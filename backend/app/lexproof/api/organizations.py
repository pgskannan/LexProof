"""Organization membership and invite endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_org_member, get_current_user, require_roles
from ..services.organizations import (
    InviteError,
    MemberNotFoundError,
    OrganizationError,
    OrganizationNotFoundError,
    OrganizationService,
    get_organization_service,
)
from ..services.regulation_map import build_regulation_map
from ..services.roles import OrgRole
from ..services.audit import record_audit_event

router = APIRouter(tags=["organizations"])


class InviteMemberRequest(BaseModel):
    email: str
    roles: list[str] = Field(min_length=1)


class UpdateRolesRequest(BaseModel):
    roles: list[str] = Field(min_length=1)


class RoleChangeRequest(BaseModel):
    role: str


class PlaybookClauseModel(BaseModel):
    clause_type: str
    standard_position: str


class UpdatePlaybookRequest(BaseModel):
    clauses: list[PlaybookClauseModel] = Field(min_length=1)


class UpdateOrgSettingsRequest(BaseModel):
    name: str | None = None
    default_link_expiry_days: int | None = Field(default=None, ge=1, le=90)
    notify_on_assignment: bool | None = None
    slack_webhook_url: str | None = None
    teams_webhook_url: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None


def _orgs() -> OrganizationService:
    return get_organization_service()


def _handle(error: OrganizationError) -> HTTPException:
    if isinstance(error, (OrganizationNotFoundError, MemberNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get("/me")
def get_me(user: dict[str, Any] = Depends(get_current_user)):
    profile = _orgs().sync_signed_in_user(
        str(user["uid"]),
        user.get("email"),
        user.get("name") or user.get("display_name"),
    )
    return profile


@router.get("/orgs/{org_id}")
def get_org(org_id: str, member: dict[str, Any] = Depends(get_current_org_member)):
    try:
        return _orgs().get_org(org_id)
    except OrganizationError as error:
        raise _handle(error) from error


@router.get("/orgs/{org_id}/settings")
def get_org_settings(org_id: str, member: dict[str, Any] = Depends(get_current_org_member)):
    """Any active member can read settings; only Admin can change them."""
    try:
        return _orgs().get_org_settings(org_id)
    except OrganizationError as error:
        raise _handle(error) from error


@router.patch("/orgs/{org_id}/settings")
def update_org_settings(
    org_id: str,
    request: UpdateOrgSettingsRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        updates = request.model_dump(exclude_unset=True)
        result = _orgs().update_org_settings(org_id, updates, str(member["uid"]))
    except OrganizationError as error:
        raise _handle(error) from error
    record_audit_event(
        actor_id=str(member["uid"]),
        actor_email=member.get("email"),
        action="org.settings_updated",
        resource_type="organization",
        resource_id=org_id,
        resource_name=result.get("name"),
        summary=f"Updated organization settings: {', '.join(sorted(updates.keys())) or 'no changes'}",
        org_id=org_id,
    )
    return result


@router.get("/orgs/{org_id}/playbook")
def get_playbook(org_id: str, member: dict[str, Any] = Depends(get_current_org_member)):
    """Any active member can read the playbook; only Admin can change it."""
    try:
        return {"clauses": _orgs().get_playbook(org_id)}
    except OrganizationError as error:
        raise _handle(error) from error


@router.put("/orgs/{org_id}/playbook")
def update_playbook(
    org_id: str,
    request: UpdatePlaybookRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        clauses = _orgs().update_playbook(org_id, [clause.model_dump() for clause in request.clauses], str(member["uid"]))
    except OrganizationError as error:
        raise _handle(error) from error
    record_audit_event(
        actor_id=str(member["uid"]),
        actor_email=member.get("email"),
        action="org.playbook_updated",
        resource_type="organization",
        resource_id=org_id,
        summary=f"Updated organization playbook ({len(clauses)} clause type(s))",
        org_id=org_id,
    )
    return {"clauses": clauses}


@router.get("/orgs/{org_id}/regulation-map")
def get_regulation_map(org_id: str, member: dict[str, Any] = Depends(get_current_org_member)):
    """Findings grouped by the specific regulation(s) they cite, across every
    contract in this org -- powers the Regulation Map view. Any active member
    can read it."""
    contracts_repo = FirestoreRepository("contracts")
    org_contracts = {
        str(contract.get("id") or contract.get("contract_id") or ""): contract
        for contract in contracts_repo.stream()
        if contract.get("org_id") == org_id
    }
    org_contracts.pop("", None)
    contract_names = {
        contract_id: str(contract.get("name") or contract.get("contract_name") or contract_id)
        for contract_id, contract in org_contracts.items()
    }
    findings_repo = FirestoreRepository("risk_findings")
    findings = [
        finding
        for finding in findings_repo.stream()
        if str(finding.get("contract_id") or "") in org_contracts
    ]
    return {"regulations": build_regulation_map(findings, contract_names)}


@router.get("/orgs/{org_id}/members")
def list_members(org_id: str, member: dict[str, Any] = Depends(get_current_org_member)):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        return _orgs().list_members(org_id)
    except OrganizationError as error:
        raise _handle(error) from error


@router.post("/orgs/{org_id}/members/invites", status_code=status.HTTP_201_CREATED)
def invite_member(
    org_id: str,
    request: InviteMemberRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        return _orgs().invite_member(org_id, request.email, request.roles, str(member["uid"]))
    except OrganizationError as error:
        raise _handle(error) from error


@router.patch("/orgs/{org_id}/members/{user_id}/roles")
def set_member_roles(
    org_id: str,
    user_id: str,
    request: UpdateRolesRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        return _orgs().set_member_roles(org_id, user_id, request.roles, str(member["uid"]))
    except OrganizationError as error:
        raise _handle(error) from error


@router.post("/orgs/{org_id}/members/{user_id}/roles")
def add_member_role(
    org_id: str,
    user_id: str,
    request: RoleChangeRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        return _orgs().add_member_role(org_id, user_id, request.role, str(member["uid"]))
    except OrganizationError as error:
        raise _handle(error) from error


@router.delete("/orgs/{org_id}/members/{user_id}/roles/{role}")
def remove_member_role(
    org_id: str,
    user_id: str,
    role: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        return _orgs().remove_member_role(org_id, user_id, role, str(member["uid"]))
    except OrganizationError as error:
        raise _handle(error) from error


@router.post("/orgs/{org_id}/members/{user_id}/deactivate")
def deactivate_member(
    org_id: str,
    user_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        return _orgs().deactivate_member(org_id, user_id, str(member["uid"]))
    except OrganizationError as error:
        raise _handle(error) from error
