"""Organization, membership, and invite management."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from ..repositories.firestore import FirestoreRepository
from .roles import OrgRole, normalize_roles

logger = logging.getLogger(__name__)

DEFAULT_ORG_ID = "lexproof-demo"
DEFAULT_ORG_NAME = "LexProof Demo"
MEMBER_ACTIVE = "active"
MEMBER_INVITED = "invited"
MEMBER_DEACTIVATED = "deactivated"

DEFAULT_ORG_SETTINGS: dict[str, Any] = {
    "default_link_expiry_days": 14,
    "notify_on_assignment": True,
    # Chat (Slack/Teams) notification webhooks: None until an admin
    # configures one. See services/chat_notifications.py -- with neither
    # set, chat notifications still fire but are recorded as simulated
    # ("stub") deliveries rather than skipped, so the feature is always
    # demoable.
    "slack_webhook_url": None,
    "teams_webhook_url": None,
    # White-label / custom branding (Task #109): None until an admin sets
    # them, in which case the app falls back to LexProof's own default
    # look (see frontend Navigation.tsx / Button.tsx) -- so every org is
    # fully branded on day one and customizing is purely additive.
    "logo_url": None,
    "primary_color": None,
}
SETTINGS_MIN_LINK_EXPIRY_DAYS = 1
SETTINGS_MAX_LINK_EXPIRY_DAYS = 90
# #rrggbb only (no shorthand #rgb, no alpha) -- kept intentionally strict
# since this value is interpolated directly into CSS custom properties on
# the frontend with no further sanitization.
PRIMARY_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Seed playbook: sensible default "standard positions" per common clause type,
# used until an org admin customizes it. Also used as the benchmark for
# contracts with no org (e.g. the demo flow), so the feature is always live,
# never gated behind org setup.
DEFAULT_PLAYBOOK_CLAUSES: list[dict[str, str]] = [
    {
        "clause_type": "Limitation of Liability",
        "standard_position": "Liability is capped at 12 months of fees paid, mutual for both parties, with "
        "standard carve-outs (fraud, gross negligence, confidentiality breach, IP indemnity).",
    },
    {
        "clause_type": "Indemnification",
        "standard_position": "Indemnification obligations are mutual and limited to third-party claims arising "
        "from breach of contract, negligence, or IP infringement -- not a broad one-sided indemnity.",
    },
    {
        "clause_type": "Intellectual Property Ownership",
        "standard_position": "The customer owns all deliverables and work product created specifically for it; "
        "each party's pre-existing IP remains with its original owner, licensed as needed to use the deliverables.",
    },
    {
        "clause_type": "Termination",
        "standard_position": "Either party may terminate for convenience with 30-90 days' written notice, or "
        "immediately for uncured material breach after a 30-day cure period.",
    },
    {
        "clause_type": "Confidentiality",
        "standard_position": "Confidentiality obligations are mutual and survive termination for 3-5 years, with "
        "standard exclusions for public and independently-developed information.",
    },
    {
        "clause_type": "Payment Terms",
        "standard_position": "Net 30 payment terms, late-payment interest capped at the statutory maximum, and "
        "no unilateral price increases without at least 60 days' notice.",
    },
    {
        "clause_type": "Governing Law",
        "standard_position": "Governing law and venue are a neutral, mutually agreeable jurisdiction -- not an "
        "exclusive forum-selection clause that only favors the drafting party.",
    },
    {
        "clause_type": "Non-Compete / Non-Solicit",
        "standard_position": "Non-solicitation of employees is limited to 12 months post-termination; no broad "
        "non-compete clause restricting the other party's general business operations.",
    },
]


class OrganizationError(ValueError):
    """Base error for organization operations."""


class OrganizationNotFoundError(OrganizationError):
    """Raised when an organization does not exist."""


class MemberNotFoundError(OrganizationError):
    """Raised when a membership record does not exist."""


class InviteError(OrganizationError):
    """Raised when an invite cannot be created or accepted."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def invite_id_for(org_id: str, email: str) -> str:
    digest = hashlib.sha256(f"{org_id}:{email.strip().lower()}".encode("utf-8")).hexdigest()[:24]
    return f"inv_{digest}"


class OrganizationService:
    def __init__(
        self,
        *,
        orgs: FirestoreRepository | None = None,
        users: FirestoreRepository | None = None,
        invites: FirestoreRepository | None = None,
        member_factory: Callable[[str], FirestoreRepository] | None = None,
        claims_refresher: Callable[[str, str, list[str]], None] | None = None,
    ) -> None:
        self.orgs = orgs or FirestoreRepository("organizations")
        self.users = users or FirestoreRepository("users")
        self.invites = invites or FirestoreRepository("organization_invites")
        self._member_factory = member_factory or (
            lambda org_id: FirestoreRepository(f"organizations/{org_id}/members")
        )
        self._claims_refresher = claims_refresher or refresh_custom_claims

    def members(self, org_id: str) -> FirestoreRepository:
        return self._member_factory(org_id)

    def create_org(
        self,
        name: str,
        created_by: str,
        *,
        org_id: str | None = None,
        creator_email: str | None = None,
        creator_display_name: str | None = None,
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        org_id = org_id or str(uuid4())
        existing = self.orgs.get(org_id)
        if existing:
            return existing
        now = _now()
        org = {
            "org_id": org_id,
            "name": name,
            "status": "active",
            "created_by": created_by,
            "created_at": now,
        }
        self.orgs.set(org_id, org)
        member_roles = normalize_roles(roles or ["admin"])
        self._upsert_member(
            org_id,
            created_by,
            roles=member_roles,
            status=MEMBER_ACTIVE,
            invited_by=created_by,
            email=creator_email,
        )
        if created_by:
            self.upsert_user(
                created_by,
                email=creator_email,
                display_name=creator_display_name,
                add_org_id=org_id,
            )
            self._refresh_claims(created_by, org_id, member_roles)
        logger.info("organization created org_id=%s actor=%s", org_id, created_by)
        return org

    def get_org(self, org_id: str) -> dict[str, Any]:
        org = self.orgs.get(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization not found: {org_id}")
        return {"org_id": org_id, **org}

    def get_org_settings(self, org_id: str) -> dict[str, Any]:
        org = self.orgs.get(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization not found: {org_id}")
        return {**DEFAULT_ORG_SETTINGS, **(org.get("settings") or {})}

    def update_org_settings(self, org_id: str, updates: dict[str, Any], actor_id: str) -> dict[str, Any]:
        org = self.orgs.get(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization not found: {org_id}")
        org_fields: dict[str, Any] = {}
        name = updates.get("name")
        if name is not None:
            name = str(name).strip()
            if not name:
                raise OrganizationError("Organization name cannot be empty")
            org_fields["name"] = name
        settings = {**DEFAULT_ORG_SETTINGS, **(org.get("settings") or {})}
        if "default_link_expiry_days" in updates and updates["default_link_expiry_days"] is not None:
            days = int(updates["default_link_expiry_days"])
            if days < SETTINGS_MIN_LINK_EXPIRY_DAYS or days > SETTINGS_MAX_LINK_EXPIRY_DAYS:
                raise OrganizationError(
                    f"default_link_expiry_days must be between {SETTINGS_MIN_LINK_EXPIRY_DAYS} and {SETTINGS_MAX_LINK_EXPIRY_DAYS}"
                )
            settings["default_link_expiry_days"] = days
        if "notify_on_assignment" in updates and updates["notify_on_assignment"] is not None:
            settings["notify_on_assignment"] = bool(updates["notify_on_assignment"])
        for webhook_key in ("slack_webhook_url", "teams_webhook_url"):
            if webhook_key not in updates:
                continue
            raw = updates[webhook_key]
            value = str(raw).strip() if raw is not None else ""
            if not value:
                settings[webhook_key] = None
            elif not value.startswith("https://"):
                raise OrganizationError(f"{webhook_key} must be a valid https:// URL")
            else:
                settings[webhook_key] = value
        if "logo_url" in updates:
            raw_logo = updates["logo_url"]
            logo_value = str(raw_logo).strip() if raw_logo is not None else ""
            if not logo_value:
                settings["logo_url"] = None
            elif not logo_value.startswith("https://"):
                raise OrganizationError("logo_url must be a valid https:// URL")
            else:
                settings["logo_url"] = logo_value
        if "primary_color" in updates:
            raw_color = updates["primary_color"]
            color_value = str(raw_color).strip() if raw_color is not None else ""
            if not color_value:
                settings["primary_color"] = None
            elif not PRIMARY_COLOR_RE.match(color_value):
                raise OrganizationError("primary_color must be a hex color like #2563EB")
            else:
                settings["primary_color"] = color_value
        org_fields["settings"] = settings
        org_fields["settings_updated_at"] = _now()
        org_fields["settings_updated_by"] = actor_id
        self.orgs.set(org_id, org_fields, merge=True)
        logger.info("organization settings updated org_id=%s actor=%s", org_id, actor_id)
        return {**DEFAULT_ORG_SETTINGS, **settings, **({"name": org_fields["name"]} if "name" in org_fields else {})}

    def get_playbook(self, org_id: str) -> list[dict[str, Any]]:
        org = self.orgs.get(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization not found: {org_id}")
        clauses = org.get("playbook_clauses")
        if isinstance(clauses, list) and clauses:
            return clauses
        return [dict(clause) for clause in DEFAULT_PLAYBOOK_CLAUSES]

    def update_playbook(self, org_id: str, clauses: list[dict[str, Any]], actor_id: str) -> list[dict[str, Any]]:
        org = self.orgs.get(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization not found: {org_id}")
        normalized: list[dict[str, Any]] = []
        for item in clauses:
            clause_type = str((item or {}).get("clause_type") or "").strip()
            standard_position = str((item or {}).get("standard_position") or "").strip()
            if not clause_type or not standard_position:
                raise OrganizationError("Each playbook clause needs both a clause_type and a standard_position")
            normalized.append({"clause_type": clause_type, "standard_position": standard_position})
        if not normalized:
            raise OrganizationError("Playbook must contain at least one clause")
        self.orgs.set(org_id, {
            "playbook_clauses": normalized,
            "playbook_updated_at": _now(),
            "playbook_updated_by": actor_id,
        }, merge=True)
        logger.info("organization playbook updated org_id=%s actor=%s clause_count=%d", org_id, actor_id, len(normalized))
        return normalized

    def get_member(self, org_id: str, user_id: str) -> dict[str, Any] | None:
        record = self.members(org_id).get(user_id)
        if not record:
            return None
        return {"user_id": user_id, "org_id": org_id, **record}

    def get_active_member(self, org_id: str, user_id: str) -> dict[str, Any] | None:
        member = self.get_member(org_id, user_id)
        if not member or member.get("status") != MEMBER_ACTIVE:
            return None
        org = self.orgs.get(org_id)
        if not org or org.get("status") == "suspended":
            return None
        return member

    def list_members(self, org_id: str) -> list[dict[str, Any]]:
        """List all members of an org, joined with each member's live
        `users/{user_id}` record for email/display_name.

        Phase 3H.5 (P1-B fix): a membership document's own `email` field is
        only ever written at membership-creation time (create_org,
        invite_member/_upsert_member, ensure_member) and reconciled later
        only via sync_signed_in_user()'s invite-acceptance loop -- which
        requires a matching organization_invites record. A membership
        created directly (e.g. by a seed/demo script) rather than through
        invite_member() has no such invite record, so its stored `email`
        can silently go stale forever even after the user's real sign-in
        updates their authoritative `users/{user_id}.email` (which
        sync_signed_in_user() DOES keep current on every sign-in). Prefer
        that live, authoritative user email here and fall back to the
        membership doc's own stored email only when no user record (or no
        email on it) exists yet -- e.g. an invited-but-not-yet-signed-in
        member. This is read-only: it changes what this listing reports,
        not any stored data, so it can't create duplicate memberships,
        doesn't touch roles/status, and doesn't affect authorization
        (get_member/get_active_member, used for auth decisions, are
        unchanged and still keyed by user_id).
        """
        self.get_org(org_id)
        members = []
        for record in self.members(org_id).stream():
            user_id = record.get("user_id") or record.get("id")
            user = self.users.get(user_id) if user_id else None
            members.append(
                {
                    **record,
                    "user_id": user_id,
                    "org_id": org_id,
                    "email": (user or {}).get("email") or record.get("email"),
                    "display_name": (user or {}).get("display_name"),
                }
            )
        return sorted(members, key=lambda item: (item.get("email") or "", item.get("user_id") or ""))

    def list_user_orgs(self, user_id: str) -> list[dict[str, Any]]:
        user = self.users.get(user_id) or {}
        org_ids = list(user.get("org_memberships") or [])
        results = []
        for org_id in org_ids:
            member = self.get_member(org_id, user_id)
            if not member or member.get("status") == MEMBER_DEACTIVATED:
                continue
            org = self.orgs.get(org_id)
            if not org:
                continue
            results.append(
                {
                    "org_id": org_id,
                    "name": org.get("name"),
                    "status": org.get("status"),
                    "roles": list(member.get("roles") or []),
                    "member_status": member.get("status"),
                }
            )
        return results

    def upsert_user(
        self,
        user_id: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
        add_org_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.users.get(user_id) or {}
        memberships = list(existing.get("org_memberships") or [])
        if add_org_id and add_org_id not in memberships:
            memberships.append(add_org_id)
        record = {
            **existing,
            "user_id": user_id,
            "email": (email or existing.get("email") or "").strip().lower() or existing.get("email"),
            "display_name": display_name or existing.get("display_name"),
            "org_memberships": memberships,
            "created_at": existing.get("created_at") or _now(),
            "updated_at": _now(),
        }
        self.users.set(user_id, record)
        return record

    def invite_member(
        self,
        org_id: str,
        email: str,
        roles: list[str],
        invited_by: str,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        self.get_org(org_id)
        normalized_email = email.strip().lower()
        if not normalized_email or "@" not in normalized_email:
            raise InviteError("A valid email is required")
        member_roles = normalize_roles(roles)
        if not member_roles:
            raise InviteError("At least one role is required")
        now = _now()
        invite_key = invite_id_for(org_id, normalized_email)
        existing_invite = self.invites.get(invite_key)
        invite = {
            "invite_id": invite_key,
            "org_id": org_id,
            "email": normalized_email,
            "roles": member_roles,
            "status": MEMBER_INVITED,
            "invited_by": invited_by,
            "created_at": (existing_invite or {}).get("created_at") or now,
            "updated_at": now,
            "user_id": user_id or (existing_invite or {}).get("user_id"),
        }
        self.invites.set(invite_key, invite)

        resolved_user_id = user_id or self._user_id_for_email(normalized_email)
        if resolved_user_id:
            self._upsert_member(
                org_id,
                resolved_user_id,
                roles=member_roles,
                status=MEMBER_INVITED,
                invited_by=invited_by,
                email=normalized_email,
            )
            invite["user_id"] = resolved_user_id
            self.invites.set(invite_key, {"user_id": resolved_user_id, "updated_at": now}, merge=True)
        logger.info("member invited org_id=%s email=%s actor=%s roles=%s", org_id, normalized_email, invited_by, member_roles)
        return invite

    def set_member_roles(self, org_id: str, user_id: str, roles: list[str], actor_id: str) -> dict[str, Any]:
        member = self.get_member(org_id, user_id)
        if not member:
            raise MemberNotFoundError(f"Member not found: {user_id}")
        member_roles = normalize_roles(roles)
        if not member_roles:
            raise OrganizationError("At least one role is required")
        updated = {
            "roles": member_roles,
            "updated_at": _now(),
            "updated_by": actor_id,
        }
        self.members(org_id).set(user_id, updated, merge=True)
        self._refresh_claims(user_id, org_id, member_roles)
        logger.info("roles updated org_id=%s actor=%s target=%s roles=%s", org_id, actor_id, user_id, member_roles)
        return {**member, **updated}

    def add_member_role(self, org_id: str, user_id: str, role: str, actor_id: str) -> dict[str, Any]:
        member = self.get_member(org_id, user_id)
        if not member:
            raise MemberNotFoundError(f"Member not found: {user_id}")
        roles = list(member.get("roles") or [])
        if role not in roles:
            roles.append(role)
        return self.set_member_roles(org_id, user_id, roles, actor_id)

    def remove_member_role(self, org_id: str, user_id: str, role: str, actor_id: str) -> dict[str, Any]:
        member = self.get_member(org_id, user_id)
        if not member:
            raise MemberNotFoundError(f"Member not found: {user_id}")
        roles = [item for item in (member.get("roles") or []) if item != role]
        if not roles:
            raise OrganizationError("A member must keep at least one role")
        return self.set_member_roles(org_id, user_id, roles, actor_id)

    def deactivate_member(self, org_id: str, user_id: str, actor_id: str) -> dict[str, Any]:
        member = self.get_member(org_id, user_id)
        if not member:
            raise MemberNotFoundError(f"Member not found: {user_id}")
        updated = {"status": MEMBER_DEACTIVATED, "updated_at": _now(), "updated_by": actor_id}
        self.members(org_id).set(user_id, updated, merge=True)
        self._refresh_claims(user_id, org_id, [])
        logger.info("member deactivated org_id=%s actor=%s target=%s", org_id, actor_id, user_id)
        return {**member, **updated}

    def sync_signed_in_user(self, user_id: str, email: str | None, display_name: str | None = None) -> dict[str, Any]:
        """Upsert the global user record and activate any matching email invites."""
        user = self.upsert_user(user_id, email=email, display_name=display_name)
        normalized_email = (email or user.get("email") or "").strip().lower()
        if normalized_email:
            for invite in self.invites.stream():
                if (invite.get("email") or "").strip().lower() != normalized_email:
                    continue
                if invite.get("status") not in {MEMBER_INVITED, MEMBER_ACTIVE}:
                    continue
                org_id = invite.get("org_id")
                if not org_id:
                    continue
                self._upsert_member(
                    org_id,
                    user_id,
                    roles=list(invite.get("roles") or ["auditor"]),
                    status=MEMBER_ACTIVE,
                    invited_by=invite.get("invited_by"),
                    email=normalized_email,
                )
                self.upsert_user(user_id, email=normalized_email, display_name=display_name, add_org_id=org_id)
                self.invites.set(
                    invite.get("invite_id") or invite.get("id"),
                    {"status": MEMBER_ACTIVE, "user_id": user_id, "accepted_at": _now(), "updated_at": _now()},
                    merge=True,
                )
                self._refresh_claims(user_id, org_id, list(invite.get("roles") or []))
                logger.info("invite accepted org_id=%s actor=%s email=%s", org_id, user_id, normalized_email)

        member = self.get_member
        for org_id in list((self.users.get(user_id) or {}).get("org_memberships") or []):
            existing = member(org_id, user_id)
            if existing and existing.get("status") == MEMBER_INVITED:
                self.members(org_id).set(
                    user_id,
                    {"status": MEMBER_ACTIVE, "joined_at": existing.get("joined_at") or _now(), "updated_at": _now()},
                    merge=True,
                )
                self._refresh_claims(user_id, org_id, list(existing.get("roles") or []))
        orgs = self.list_user_orgs(user_id)
        return {"user_id": user_id, "email": normalized_email, "display_name": display_name, "orgs": orgs}

    def ensure_member(
        self,
        org_id: str,
        user_id: str,
        roles: list[str],
        *,
        email: str | None = None,
        status: str = MEMBER_ACTIVE,
        invited_by: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_member(org_id, user_id)
        merged_roles = normalize_roles(list(existing.get("roles") or []) + list(roles) if existing else roles)
        self._upsert_member(
            org_id,
            user_id,
            roles=merged_roles,
            status=status if not existing else existing.get("status") or status,
            invited_by=invited_by or (existing or {}).get("invited_by"),
            email=email or (existing or {}).get("email"),
        )
        self.upsert_user(user_id, email=email, add_org_id=org_id)
        return self.get_member(org_id, user_id) or {}

    def _upsert_member(
        self,
        org_id: str,
        user_id: str,
        *,
        roles: list[str],
        status: str,
        invited_by: str | None,
        email: str | None,
    ) -> None:
        existing = self.members(org_id).get(user_id) or {}
        now = _now()
        record = {
            **existing,
            "user_id": user_id,
            "org_id": org_id,
            "roles": roles,
            "status": status,
            "email": (email or existing.get("email") or "").strip().lower() or existing.get("email"),
            "invited_by": invited_by or existing.get("invited_by"),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
        }
        if status == MEMBER_ACTIVE and not existing.get("joined_at"):
            record["joined_at"] = now
        self.members(org_id).set(user_id, record)

    def _user_id_for_email(self, email: str) -> str | None:
        for user in self.users.stream():
            if (user.get("email") or "").strip().lower() == email:
                return user.get("user_id") or user.get("id")
        return None

    def _refresh_claims(self, user_id: str, org_id: str, roles: list[str]) -> None:
        try:
            self._claims_refresher(user_id, org_id, roles)
        except Exception as exc:
            logger.warning("custom claims refresh failed uid=%s org_id=%s: %s", user_id, org_id, exc)


def refresh_custom_claims(user_id: str, org_id: str, roles: list[str]) -> None:
    """Best-effort Firebase custom-claims cache for frontend UX. Not an authz source of truth."""
    try:
        from .firebase import initialize_firebase
        from firebase_admin import auth

        initialize_firebase()
        auth.set_custom_user_claims(user_id, {"org_id": org_id, "roles": roles})
    except Exception as exc:
        logger.warning("custom claims not updated uid=%s: %s", user_id, exc)


def get_organization_service() -> OrganizationService:
    return OrganizationService()


def contract_owner_or_org_admin(contract: dict[str, Any], user_id: str) -> bool:
    """True if `user_id` is the contract's real owner, or an active Admin of
    the contract's organization.

    Several owner-gated contract actions (analyze, create a new version)
    historically used a bare `contract.get("owner_id") == user_id` check,
    independent of the organization/role model enforced everywhere else
    (api/contracts.py::_is_visible_to_user, and the owner-or-admin rule
    services/redline_proposals.py already applies to proposal creation and
    editing). That meant a legitimate org Admin could see a contract but not
    act on it if they were not the original uploader -- Phase 1/2 audit P1.

    This mirrors the already-established owner-or-admin rule instead of
    inventing a new one: the actual owner may always act; within an
    organization, an active Admin may also act on any contract in that same
    org; a non-owner, non-admin member (Reviewer/Approver/Auditor/
    Contract Owner-role-but-not-actual-owner) is still rejected; a member of
    a different organization or a non-member is rejected; and a contract
    with no org_id (legacy data) keeps the strict, owner-only behavior it
    always had.
    """
    if contract.get("owner_id") == user_id:
        return True
    org_id = contract.get("org_id")
    if not org_id:
        return False
    member = get_organization_service().get_active_member(str(org_id), user_id)
    return bool(member and OrgRole.ADMIN.value in (member.get("roles") or []))
