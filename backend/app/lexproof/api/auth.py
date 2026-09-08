"""Compatibility export for the shared authentication dependency."""

from ..services.auth import (
    get_current_org_member,
    get_current_org_member_from_header,
    get_current_user,
    require_roles,
)

__all__ = [
    "get_current_user",
    "get_current_org_member",
    "get_current_org_member_from_header",
    "require_roles",
]
