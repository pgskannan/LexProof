"""Org-scoped workflow definition and instance endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..services.auth import get_current_org_member, require_roles
from ..services.roles import OrgRole
from ..services.workflow_engine import (
    WorkflowError,
    WorkflowNotFoundError,
    WorkflowPermissionError,
    WorkflowSeparationOfDutiesError,
    WorkflowTransitionError,
    get_workflow_engine,
)

router = APIRouter(prefix="/orgs/{org_id}", tags=["workflows"])


class WorkflowStateInput(BaseModel):
    id: str
    name: str
    is_initial: bool = False
    is_terminal: bool = False


class WorkflowTransitionInput(BaseModel):
    id: str
    from_state: str
    to_state: str
    action_name: str
    allowed_roles: list[str] = Field(default_factory=list)
    requires_not_actor: list[str] = Field(default_factory=list)


class WorkflowDefinitionCreateRequest(BaseModel):
    name: str
    states: list[WorkflowStateInput]
    transitions: list[WorkflowTransitionInput]


class WorkflowTransitionRequest(BaseModel):
    transition_id: str
    comment: str | None = None


def _handle(error: WorkflowError) -> HTTPException:
    if isinstance(error, WorkflowNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, (WorkflowPermissionError, WorkflowSeparationOfDutiesError)):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, WorkflowTransitionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get("/workflow-definitions")
def list_workflow_definitions(
    org_id: str,
    name: str | None = Query(None),
    member: dict[str, Any] = Depends(get_current_org_member),
):
    return get_workflow_engine().list_definitions(org_id, name)


@router.get("/workflow-definitions/{definition_id}")
def get_workflow_definition(
    org_id: str,
    definition_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    try:
        definition = get_workflow_engine().get_definition(definition_id)
    except WorkflowError as error:
        raise _handle(error) from error
    if definition.get("org_id") != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow definition not found")
    return definition


@router.post("/workflow-definitions", status_code=status.HTTP_201_CREATED)
def create_workflow_definition(
    org_id: str,
    request: WorkflowDefinitionCreateRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    require_roles(member, OrgRole.ADMIN.value)
    try:
        return get_workflow_engine().create_definition(
            org_id,
            request.name,
            [state.model_dump() for state in request.states],
            [item.model_dump() for item in request.transitions],
            str(member["uid"]),
        )
    except WorkflowError as error:
        raise _handle(error) from error


@router.get("/workflow-instances")
def list_workflow_instances(
    org_id: str,
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    instance_status: str | None = Query(None, alias="status"),
    assigned_role: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    member: dict[str, Any] = Depends(get_current_org_member),
):
    return get_workflow_engine().list_instances(
        org_id,
        entity_type=entity_type,
        status=instance_status,
        assigned_role=assigned_role,
        entity_id=entity_id,
        limit=limit,
        cursor=cursor,
    )


@router.get("/workflow-instances/{instance_id}")
def get_workflow_instance(
    org_id: str,
    instance_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    try:
        instance = get_workflow_engine().get_instance(instance_id)
    except WorkflowError as error:
        raise _handle(error) from error
    if instance.get("org_id") != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow instance not found")
    return instance


@router.get("/workflow-instances/{instance_id}/history")
def get_workflow_instance_history(
    org_id: str,
    instance_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    try:
        instance = get_workflow_engine().get_instance(instance_id)
        if instance.get("org_id") != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow instance not found")
        return get_workflow_engine().get_instance_history(instance_id)
    except HTTPException:
        raise
    except WorkflowError as error:
        raise _handle(error) from error


@router.post("/workflow-instances/{instance_id}/transitions")
def execute_workflow_transition(
    org_id: str,
    instance_id: str,
    request: WorkflowTransitionRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    try:
        instance = get_workflow_engine().get_instance(instance_id)
        if instance.get("org_id") != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow instance not found")
        return get_workflow_engine().execute_transition(
            instance_id,
            request.transition_id,
            str(member["uid"]),
            list(member.get("roles") or []),
            request.comment,
        )
    except HTTPException:
        raise
    except WorkflowError as error:
        raise _handle(error) from error
