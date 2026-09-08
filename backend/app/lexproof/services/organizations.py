"""Organization, membership, and invite management."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from ..repositories.firestore import FirestoreRepository
from .roles import normalize_roles

logger = logging.getLogger(__name__)

DEFAULT_ORG_ID = "lexproof-demo"
DEFAULT_ORG_NAME = "LexProof Demo"
MEMBER_ACTIVE = "active"
MEMBER_INVITED = "invited"
MEMBER_DEACTIVATED = "deactivated"

DEFAULT_ORG_SETTINGS: dict[str, Any] = {
    "default_link_expiry_days": 14,
    "notify_on_assignment": True,
}
SETTINGS_MIN_LINK_EXPIRY_DAYS = 1
SETTINGS_MAX_LINK_EXPIRY_DAYS = 90


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
        org_fields["settings"] = settings
        org_fields["settings_updated_at"] = _now()
        org_fields["settings_updated_by"] = actor_id
        self.orgs.set(org_id, org_fields, merge=True)
        logger.info("organization settings updated org_id=%s actor=%s", org_id, actor_id)
        return {**DEFAULT_ORG_SETTINGS, **settings, **({"name": org_fields["name"]} if "name" in org_fields else {})}

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
                    "email": record.get("email") or (user or {}).get("email"),
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
