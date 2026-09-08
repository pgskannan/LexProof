"""Shared FastAPI authentication dependency."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .firebase_auth import FirebaseAuthenticationError, verify_firebase_token
from .roles import has_any_role

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
ORG_ID_HEADER = "X-Org-Id"


def get_current_user(
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
