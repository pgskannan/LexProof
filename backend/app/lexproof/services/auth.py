"""Shared FastAPI authentication dependency."""

from __future__ import annotations

import logging
import os
import re
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .firebase_auth import FirebaseAuthenticationError, verify_firebase_token
from .roles import has_any_role

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
ORG_ID_HEADER = "X-Org-Id"

# Read-only accounts (e.g. the public hackathon judge login): their UIDs are
# listed in LEXPROOF_READ_ONLY_UIDS. They can sign in and see everything their
# org membership allows, but any request that would change data is refused.
READ_ONLY_UIDS_ENV = "LEXPROOF_READ_ONLY_UIDS"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Non-GET endpoints that only read, or only touch the caller's own UI state.
_READ_ONLY_ALLOWED_WRITES = tuple(
    re.compile(pattern)
    for pattern in (
        r"/ask$",                                  # Ask Lexi (answers a question)
        r"/translate$",                            # translate findings for display
        r"/verify$",                               # re-run an integrity check
        r"/verify-version-history/[^/]+$",
        r"/portfolio-snapshots$",                  # daily trend snapshot captured on page load
        r"/preferences/ui$",                       # the caller's own dashboard layout
        r"/notifications/(read-all|[^/]+/read)$",  # mark the caller's notifications read
    )
)
READ_ONLY_DETAIL = "This is a read-only demo account: you can explore everything, but changes are disabled."


def read_only_uids() -> set[str]:
    return {uid.strip() for uid in os.getenv(READ_ONLY_UIDS_ENV, "").split(",") if uid.strip()}


def enforce_read_only(uid: str, method: str, path: str) -> None:
    if method.upper() in _SAFE_METHODS or uid not in read_only_uids():
        return
    if any(pattern.search(path.rstrip("/")) for pattern in _READ_ONLY_ALLOWED_WRITES):
        return
    logger.info("read-only account blocked actor=%s method=%s path=%s", uid, method, path)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=READ_ONLY_DETAIL)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is required", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = verify_firebase_token(credentials.credentials)
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    if not claims.get("uid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firebase token does not contain a UID", headers={"WWW-Authenticate": "Bearer"})
    enforce_read_only(str(claims["uid"]), request.method, request.url.path)
    return claims


def get_org_id_from_header(
    x_org_id: Annotated[str | None, Header(alias=ORG_ID_HEADER)] = None,
) -> str:
    if not x_org_id or not str(x_org_id).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Org-Id header is required")
    return str(x_org_id).strip()


def load_org_member(org_id: str, user: dict[str, Any]) -> dict[str, Any]:
    from .organizations import get_organization_service

    uid = str(user.get("uid") or "")
    member = get_organization_service().get_active_member(org_id, uid)
    if not member:
        logger.warning("permission denied org_id=%s actor=%s action=org_membership", org_id, uid)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an active member of this organization",
        )
    return {
        **user,
        "org_id": org_id,
        "roles": list(member.get("roles") or []),
        "member_status": member.get("status"),
    }


def get_current_org_member(
    org_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Path-param variant: verifies the Firebase token, then Firestore membership for `org_id`."""
    return load_org_member(org_id, user)


def get_current_org_member_from_header(
    org_id: str = Depends(get_org_id_from_header),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Header variant for endpoints that do not include org_id in the path."""
    return load_org_member(org_id, user)


def require_roles(member: dict[str, Any], *roles: str) -> dict[str, Any]:
    held = list(member.get("roles") or [])
    if has_any_role(held, roles):
        return member
    logger.warning(
        "permission denied org_id=%s actor=%s action=require_roles required=%s held=%s",
        member.get("org_id"),
        member.get("uid"),
        roles,
        held,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not authorized to perform this action",
    )
