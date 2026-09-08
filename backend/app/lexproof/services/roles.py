"""Fixed organization roles. Values are stored as strings in Firestore."""

from __future__ import annotations

from enum import Enum


class OrgRole(str, Enum):
    ADMIN = "admin"
    CONTRACT_OWNER = "contract_owner"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    AUDITOR = "auditor"


ALL_ROLES = tuple(role.value for role in OrgRole)
ADMIN_ROLES = (OrgRole.ADMIN.value,)
MEMBER_MANAGEMENT_ROLES = (OrgRole.ADMIN.value,)
WORKFLOW_DEFINITION_ROLES = (OrgRole.ADMIN.value,)


def normalize_roles(roles: list[str] | tuple[str, ...] | None) -> list[str]:
    unique: list[str] = []
    for role in roles or []:
        value = str(role).strip().lower()
        if value not in ALL_ROLES:
            raise ValueError(f"Unknown role: {role}")
        if value not in unique:
            unique.append(value)
    return unique


def has_any_role(held: list[str] | tuple[str, ...] | None, required: list[str] | tuple[str, ...] | None) -> bool:
    if not required:
        return True
    held_set = set(held or [])
    return bool(held_set.intersection(required))
