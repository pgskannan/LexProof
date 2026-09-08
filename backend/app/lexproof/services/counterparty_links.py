"""Scoped, token-based access links for external counterparties.

The opaque link token is the entire credential. Counterparties never receive a
Firebase account, password, or org membership. Countersignatures are recorded
as ordinary evidence items; this module does not touch workflow state.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from ..config import get_settings
from ..domains.passport.evidence_service import EvidenceService
from ..domains.passport.models import EvidenceItemCreate, EvidenceStatus, EvidenceType
from ..domains.passport.utils.hashing import compute_sha256_hash
from ..repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository, FirestoreRepository
from .organizations import OrganizationService, get_organization_service
from .roles import OrgRole, has_any_role

logger = logging.getLogger(__name__)

COLLECTION = "external_access_links"
DEFAULT_PERMISSIONS = ("view", "comment", "countersign")
ALLOWED_PERMISSIONS = frozenset(DEFAULT_PERMISSIONS)
DEFAULT_EXPIRY_DAYS = 14
MAX_EXPIRY_DAYS = 90
MIN_EXPIRY_DAYS = 1
MAX_COMMENTS_PER_LINK = 25
MAX_COMMENT_LENGTH = 2000
TOKEN_BYTES = 32
MIN_TOKEN_LENGTH = 16
LINK_CREATE_ROLES = (OrgRole.ADMIN.value, OrgRole.CONTRACT_OWNER.value)
COUNTERSIGNABLE_STATUSES = frozenset({"APPROVED", "PUBLISHED"})
ATTESTATION_STATEMENT = "I have reviewed this redline and agree to be bound by it"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_RATE_LIMIT_GET = (60, 60)
_RATE_LIMIT_COMMENT = (10, 60)
_RATE_LIMIT_COUNTERSIGN = (5, 60)


class CounterpartyLinkError(ValueError):
    """Base error for counterparty link operations."""


class LinkNotFoundError(CounterpartyLinkError):
    """Raised when a token does not match an existing link."""


class LinkExpiredError(CounterpartyLinkError):
    """Raised when the link has passed its expiry."""


class LinkRevokedError(CounterpartyLinkError):
    """Raised when the link has been revoked."""


class LinkPermissionError(CounterpartyLinkError):
    """Raised when the link does not grant the requested permission."""


class LinkAlreadyCountersignedError(CounterpartyLinkError):
    """Raised when a second countersignature is attempted on the same link."""


class LinkRateLimitedError(CounterpartyLinkError):
    """Raised when an unauthenticated endpoint is used too frequently."""


class CommentCapError(CounterpartyLinkError):
    """Raised when a link has reached its comment cap."""


class CountersignNotReadyError(CounterpartyLinkError):
    """Raised when the proposal is not in a countersignable status."""


class TokenRateLimiter:
    """In-memory sliding-window limiter keyed by token hash, not the raw token."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, max_hits: int, window_seconds: int) -> bool:
        now = time.monotonic()
        window_start = now - window_seconds
        hits = [stamp for stamp in self._hits.get(key, []) if stamp > window_start]
        if len(hits) >= max_hits:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = TokenRateLimiter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def token_document_id(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def frontend_origin() -> str:
    origins = get_settings().cors_origin_list()
    return (origins[0] if origins else "http://localhost:3000").rstrip("/")


def share_url_for(token: str) -> str | None:
    if not token:
        return None
    return f"{frontend_origin()}/counterparty/{token}"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _public_link(record: dict[str, Any], *, include_token: bool = False) -> dict[str, Any]:
    token = record.get("token") or ""
    payload = {
        "token_id": record.get("token_id"),
        "org_id": record.get("org_id"),
        "contract_id": record.get("contract_id"),
        "contract_version": record.get("contract_version"),
        "redline_proposal_id": record.get("redline_proposal_id"),
        "created_by": record.get("created_by"),
        "created_at": record.get("created_at"),
        "expires_at": record.get("expires_at"),
        "revoked": bool(record.get("revoked")),
        "counterparty_name": record.get("counterparty_name"),
        "counterparty_email": record.get("counterparty_email"),
        "permissions": list(record.get("permissions") or []),
        "countersigned": bool(record.get("countersign_evidence_id")),
        "countersigned_at": record.get("countersigned_at"),
        "countersign_evidence_id": record.get("countersign_evidence_id"),
        "comment_count": len(record.get("comments") or []),
    }
    if include_token:
        payload["token"] = token
        payload["share_path"] = f"/counterparty/{token}" if token else None
        payload["share_url"] = share_url_for(token)
    return payload


class CounterpartyLinkService:
    def __init__(
        self,
        *,
        links: FirestoreRepository | None = None,
        contracts: FirestoreRepository | None = None,
        versions: FirestoreRepository | None = None,
        proposals: FirestoreRepository | None = None,
        passports: FirestoreRepository | None = None,
        evidence_records: FirestoreRepository | None = None,
        organizations: OrganizationService | None = None,
        evidence_service_factory: Callable[[str], EvidenceService] | None = None,
        limiter: TokenRateLimiter | None = None,
    ) -> None:
        self.links = links or FirestoreRepository(COLLECTION)
        self.contracts = contracts or FirestoreRepository("contracts")
        self.versions = versions or FirestoreRepository("contract_versions")
        self.proposals = proposals or FirestoreRepository("redline_proposals")
        self.passports = passports or FirestoreRepository("legal_passports")
        self.evidence_records = evidence_records
        self.organizations = organizations or get_organization_service()
        self._evidence_service_factory = evidence_service_factory
        self.limiter = limiter or rate_limiter

    def _evidence_service(self, owner_id: str) -> EvidenceService:
        if self._evidence_service_factory:
            return self._evidence_service_factory(owner_id)
        anchor_repository = EvidenceAnchorRepository("evidence_anchors")
        repository = self.evidence_records or EvidenceRecordRepository(anchor_repository)
        return EvidenceService(
            repository,
            owner_id=owner_id,
            passport_repository=self.passports,
            anchor_repository=anchor_repository,
        )

    def create_link(
        self,
        org_id: str,
        contract_id: str,
        *,
        redline_proposal_id: str,
        counterparty_name: str,
        counterparty_email: str,
        created_by: str,
        expires_in_days: int | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        roles = self._require_creator(org_id, created_by)
        contract = self._require_org_contract(org_id, contract_id)
        proposal = self.proposals.get(redline_proposal_id)
        if not proposal:
            raise CounterpartyLinkError(f"Redline proposal not found: {redline_proposal_id}")
        if proposal.get("contract_id") != contract_id:
            raise CounterpartyLinkError("Proposal does not belong to this contract")
        name = (counterparty_name or "").strip()
        email = (counterparty_email or "").strip().lower()
        if not name:
            raise CounterpartyLinkError("Counterparty name is required")
        if not email or not EMAIL_RE.match(email):
            raise CounterpartyLinkError("A valid counterparty email is required")
        if expires_in_days is None:
            try:
                org_settings = self.organizations.get_org_settings(org_id)
                days = int(org_settings.get("default_link_expiry_days") or DEFAULT_EXPIRY_DAYS)
            except Exception:
                # Org-level default is a convenience only -- never block link
                # creation because the settings lookup itself failed.
                days = DEFAULT_EXPIRY_DAYS
        else:
            days = int(expires_in_days)
        if days < MIN_EXPIRY_DAYS or days > MAX_EXPIRY_DAYS:
            raise CounterpartyLinkError(f"Expiry must be between {MIN_EXPIRY_DAYS} and {MAX_EXPIRY_DAYS} days")
        granted = list(permissions or DEFAULT_PERMISSIONS)
        unknown = [item for item in granted if item not in ALLOWED_PERMISSIONS]
        if unknown:
            raise CounterpartyLinkError(f"Unknown permission: {unknown[0]}")
        if "view" not in granted:
            granted.insert(0, "view")
        source_version_id = proposal.get("source_version_id")
        source = self.versions.get(source_version_id) if source_version_id else None
        contract_version = (source or {}).get("version_number") or contract.get("version") or 1
        token = generate_token()
        token_id = str(uuid4())
        document_id = token_document_id(token)
        now = _now()
        record = {
            "token": token,
            "token_id": token_id,
            "org_id": org_id,
            "contract_id": contract_id,
            "contract_version": contract_version,
            "redline_proposal_id": redline_proposal_id,
            "created_by": created_by,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=days)).isoformat(),
            "revoked": False,
            "counterparty_name": name,
            "counterparty_email": email,
            "permissions": granted,
            "comments": [],
            "countersigned": False,
            "countersign_evidence_id": None,
            "countersign_lock": False,
        }
        self.links.set(document_id, record)
        logger.info(
            "counterparty link created org_id=%s token_id=%s contract_id=%s proposal_id=%s actor=%s roles=%s",
            org_id,
            token_id,
            contract_id,
            redline_proposal_id,
            created_by,
            roles,
        )
        return _public_link(record, include_token=True)

    def list_links(self, org_id: str, contract_id: str, actor_id: str, redline_proposal_id: str | None = None) -> list[dict[str, Any]]:
        self._require_creator(org_id, actor_id)
        self._require_org_contract(org_id, contract_id)
        records: list[dict[str, Any]] = []
        if hasattr(self.links, "query"):
            equal: dict[str, Any] = {"org_id": org_id, "contract_id": contract_id}
            if redline_proposal_id:
                equal["redline_proposal_id"] = redline_proposal_id
            try:
                records = self.links.query(equal=equal)
            except Exception as exc:
                logger.warning("counterparty link query failed org_id=%s: %s", org_id, exc)
                records = []
        if not records:
            records = [
                item
                for item in self.links.stream()
                if item.get("org_id") == org_id
                and item.get("contract_id") == contract_id
                and (redline_proposal_id is None or item.get("redline_proposal_id") == redline_proposal_id)
            ]
        records.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return [_public_link(item) for item in records]

    def get_external_view(self, token: str) -> dict[str, Any]:
        record = self._authenticate_token(token, "view", *_RATE_LIMIT_GET)
        proposal = self.proposals.get(record["redline_proposal_id"]) or {}
        contract = self.contracts.get(record["contract_id"]) or {}
        comments = [
            {
                "comment_id": item.get("comment_id"),
                "author_name": item.get("author_name"),
                "body": item.get("body"),
                "created_at": item.get("created_at"),
            }
            for item in (record.get("comments") or [])
        ]
        return {
            "contract_name": contract.get("name") or contract.get("contract_name") or "Contract",
            "contract_version": record.get("contract_version"),
            "proposal_status": proposal.get("status"),
            "title": proposal.get("title"),
            "original_text": proposal.get("original_text") or "",
            "proposed_text": proposal.get("proposed_text") or "",
            "recommendation": proposal.get("recommendation"),
            "reason": proposal.get("reason"),
            "counterparty_name": record.get("counterparty_name"),
            "permissions": list(record.get("permissions") or []),
            "expires_at": record.get("expires_at"),
            "already_countersigned": bool(record.get("countersign_evidence_id")),
            "countersign_evidence_id": record.get("countersign_evidence_id"),
            "attestation_statement": ATTESTATION_STATEMENT,
            "comments": comments,
        }

    def add_comment(self, token: str, body: str) -> dict[str, Any]:
        record = self._authenticate_token(token, "comment", *_RATE_LIMIT_COMMENT)
        text = (body or "").strip()
        if not text:
            raise CounterpartyLinkError("Comment cannot be empty")
        if len(text) > MAX_COMMENT_LENGTH:
            raise CounterpartyLinkError(f"Comment cannot exceed {MAX_COMMENT_LENGTH} characters")
        comments = list(record.get("comments") or [])
        if len(comments) >= MAX_COMMENTS_PER_LINK:
            raise CommentCapError(f"This link allows at most {MAX_COMMENTS_PER_LINK} comments")
        comment = {
            "comment_id": str(uuid4()),
            "author_name": record.get("counterparty_name"),
            "body": text,
            "created_at": _now_iso(),
        }
        comments.append(comment)
        self.links.set(token_document_id(token), {"comments": comments}, merge=True)
        logger.info(
            "counterparty comment added token_id=%s comment_id=%s",
            record.get("token_id"),
            comment["comment_id"],
        )
        return comment

    async def countersign(self, token: str, typed_name: str, attestation_accepted: bool) -> dict[str, Any]:
        record = self._authenticate_token(token, "countersign", *_RATE_LIMIT_COUNTERSIGN)
        if record.get("countersign_evidence_id") or record.get("countersigned"):
            raise LinkAlreadyCountersignedError("This link has already been used to countersign")
        name = (typed_name or "").strip()
        expected = (record.get("counterparty_name") or "").strip()
        if not name:
            raise CounterpartyLinkError("You must type your name to countersign")
        if name.casefold() != expected.casefold():
            raise CounterpartyLinkError("Typed name must match the name this link was issued to")
        if not attestation_accepted:
            raise CounterpartyLinkError("You must accept the attestation to countersign")
        proposal = self.proposals.get(record["redline_proposal_id"])
        if not proposal:
            raise CounterpartyLinkError("Redline proposal not found")
        status = (proposal.get("status") or "").upper()
        if status not in COUNTERSIGNABLE_STATUSES:
            raise CountersignNotReadyError(
                "This redline has not been internally approved, so it cannot be countersigned yet"
            )
        document_id = token_document_id(token)
        claimed = self._claim_countersign(document_id, record)
        if claimed.get("countersign_evidence_id"):
            raise LinkAlreadyCountersignedError("This link has already been used to countersign")
        try:
            evidence = await self._record_countersignature_evidence(record, name)
        except Exception:
            self.links.set(document_id, {"countersign_lock": False, "countersigned": False}, merge=True)
            raise
        now = _now_iso()
        self.links.set(
            document_id,
            {
                "countersigned": True,
                "countersign_lock": False,
                "countersigned_at": now,
                "countersign_evidence_id": evidence.evidence_id,
            },
            merge=True,
        )
        logger.info(
            "counterparty countersigned token_id=%s evidence_id=%s proposal_id=%s",
            record.get("token_id"),
            evidence.evidence_id,
            record.get("redline_proposal_id"),
        )
        return {
            "evidence_id": evidence.evidence_id,
            "hash": evidence.hash,
            "passport_id": evidence.passport_id,
            "created_at": evidence.created_at.isoformat() if evidence.created_at else now,
        }

    def _claim_countersign(self, document_id: str, record: dict[str, Any]) -> dict[str, Any]:
        def apply(transaction: Any) -> dict[str, Any]:
            current = self.links.get(document_id, transaction=transaction) or record
            if current.get("countersign_evidence_id") or current.get("countersigned"):
                raise LinkAlreadyCountersignedError("This link has already been used to countersign")
            if current.get("countersign_lock"):
                raise LinkAlreadyCountersignedError("This link has already been used to countersign")
            self.links.set(document_id, {"countersign_lock": True}, merge=True, transaction=transaction)
            return {**current, "countersign_lock": True}

        if hasattr(self.links, "run_transaction"):
            return self.links.run_transaction(apply)
        return apply(None)

    async def _record_countersignature_evidence(self, record: dict[str, Any], signed_name: str) -> Any:
        timestamp = _now_iso()
        payload = {
            "token_id": record.get("token_id"),
            "contract_version": record.get("contract_version"),
            "redline_proposal_id": record.get("redline_proposal_id"),
            "counterparty_name": signed_name,
            "timestamp": timestamp,
            "attestation": ATTESTATION_STATEMENT,
        }
        payload_hash = compute_sha256_hash(payload)
        passport = self._resolve_passport(record)
        if not passport:
            raise CounterpartyLinkError(
                "This contract version does not yet have a Legal Passport, so a countersignature cannot be recorded as evidence"
            )
        passport_id = passport.get("passport_id") or passport.get("id")
        contract = self.contracts.get(record["contract_id"]) or {}
        owner_id = contract.get("owner_id") or record.get("created_by") or "counterparty"
        evidence_service = self._evidence_service(str(owner_id))
        created = await evidence_service.create_evidence_item(
            passport_id,
            EvidenceItemCreate(
                passport_id=passport_id,
                evidence_type=EvidenceType.COUNTERPARTY_COUNTERSIGNATURE,
                title=f"Counterparty countersignature — {signed_name}",
                description=(
                    f"{signed_name} reviewed this redline and agreed to be bound by it. "
                    "The countersignature is cryptographically recorded as evidence on this contract's Legal Passport."
                ),
                content=json.dumps(payload, sort_keys=True, ensure_ascii=False),
                content_type="application/json",
                evidence_status=EvidenceStatus.VALID,
                contract_reference=record.get("redline_proposal_id"),
                source="counterparty_countersign",
                source_id=record.get("token_id"),
                metadata={
                    "token_id": record.get("token_id"),
                    "redline_proposal_id": record.get("redline_proposal_id"),
                    "contract_id": record.get("contract_id"),
                    "contract_version": record.get("contract_version"),
                    "counterparty_name": signed_name,
                    "attestation": ATTESTATION_STATEMENT,
                    "payload_hash": payload_hash,
                },
            ),
            user=None,
        )
        if evidence_service.repository:
            extra = {
                "contract_id": record.get("contract_id"),
                "contract_version": record.get("contract_version"),
            }
            evidence_service.repository.set(created.evidence_id, extra, merge=True)
        return created

    def _resolve_passport(self, record: dict[str, Any]) -> dict[str, Any] | None:
        proposal = self.proposals.get(record.get("redline_proposal_id") or "") or {}
        version_ids = [proposal.get("published_version_id"), proposal.get("source_version_id")]
        for version_id in version_ids:
            if not version_id:
                continue
            version = self.versions.get(version_id)
            if not version:
                continue
            passport_id = version.get("passport_id")
            if passport_id:
                passport = self.passports.get(passport_id)
                if passport:
                    return {"passport_id": passport_id, **passport}
        contract_id = record.get("contract_id")
        version_number = record.get("contract_version")
        matches = [
            {"passport_id": item.get("passport_id") or item.get("id"), **item}
            for item in self.passports.stream()
            if item.get("contract_id") == contract_id
            and (version_number is None or item.get("contract_version") == version_number)
        ]
        if matches:
            matches.sort(key=lambda item: item.get("contract_version") or 0, reverse=True)
            return matches[0]
        fallback = [
            {"passport_id": item.get("passport_id") or item.get("id"), **item}
            for item in self.passports.stream()
            if item.get("contract_id") == contract_id
        ]
        if not fallback:
            return None
        fallback.sort(key=lambda item: item.get("contract_version") or 0, reverse=True)
        return fallback[0]

    def _authenticate_token(self, token: str, permission: str, max_hits: int, window_seconds: int) -> dict[str, Any]:
        presented = (token or "").strip()
        key = token_document_id(presented) if presented else "empty"
        if not self.limiter.allow(key, max_hits, window_seconds):
            logger.warning("counterparty rate limited permission=%s token_id_hash=%s", permission, key[:12])
            raise LinkRateLimitedError("Too many requests for this link. Please try again shortly.")
        if len(presented) < MIN_TOKEN_LENGTH:
            raise LinkNotFoundError("This access link is invalid or no longer available")
        record = self.links.get(key)
        if not record:
            raise LinkNotFoundError("This access link is invalid or no longer available")
        stored_token = record.get("token") or ""
        if stored_token and not hmac.compare_digest(stored_token, presented):
            raise LinkNotFoundError("This access link is invalid or no longer available")
        if record.get("revoked"):
            raise LinkRevokedError("This access link has been revoked")
        expires_at = _parse_iso(record.get("expires_at"))
        if expires_at is not None and expires_at <= _now():
            raise LinkExpiredError("This access link has expired")
        granted = list(record.get("permissions") or [])
        if permission not in granted:
            raise LinkPermissionError(f"This link does not allow {permission}")
        return {**record, "id": key}

    def _require_creator(self, org_id: str, user_id: str) -> list[str]:
        member = self.organizations.get_active_member(org_id, user_id)
        if not member:
            logger.warning("permission denied org_id=%s actor=%s action=counterparty_link_membership", org_id, user_id)
            raise PermissionError("You are not authorized to manage counterparty links")
        roles = list(member.get("roles") or [])
        if not has_any_role(roles, LINK_CREATE_ROLES):
            logger.warning(
                "permission denied org_id=%s actor=%s action=counterparty_link_create required=%s held=%s",
                org_id,
                user_id,
                LINK_CREATE_ROLES,
                roles,
            )
            raise PermissionError("You are not authorized to manage counterparty links")
        return roles

    def _require_org_contract(self, org_id: str, contract_id: str) -> dict[str, Any]:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise CounterpartyLinkError(f"Contract not found: {contract_id}")
        if contract.get("org_id") != org_id:
            raise CounterpartyLinkError("Contract does not belong to this organization")
        return contract


def get_counterparty_link_service() -> CounterpartyLinkService:
    return CounterpartyLinkService()
