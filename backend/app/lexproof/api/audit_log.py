"""Cross-cutting audit log: read-only feed of major mutating actions across
this organization (contract uploads, AI analysis completions, redline
review/publish decisions, compliance approvals, ...).

Entries are written by services/audit.py from the individual endpoints that
perform those actions; this module only reads them back, scoped to the
caller's organization and gated to the Admin/Auditor roles (the Auditor role
existed in the RBAC model with nothing that actually used it until now).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_org_member_from_header, require_roles
from ..services.roles import OrgRole

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


class AuditLogEntryResponse(BaseModel):
    id: str
    actor_id: str
    actor_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    summary: str
    org_id: Optional[str] = None
    metadata: dict[str, Any] = {}
    created_at: Optional[datetime] = None


def _response(record: dict[str, Any]) -> AuditLogEntryResponse:
    return AuditLogEntryResponse(
        id=str(record.get("id") or ""),
        actor_id=str(record.get("actor_id") or ""),
        actor_email=record.get("actor_email"),
        action=str(record.get("action") or ""),
        resource_type=str(record.get("resource_type") or ""),
        resource_id=record.get("resource_id"),
        resource_name=record.get("resource_name"),
        summary=str(record.get("summary") or ""),
        org_id=record.get("org_id"),
        metadata=record.get("metadata") or {},
        created_at=record.get("created_at"),
    )


@router.get("", response_model=list[AuditLogEntryResponse])
def list_audit_log(
    limit: int = Query(100, ge=1, le=500),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
) -> list[AuditLogEntryResponse]:
    """Return this organization's audit-log entries, most recent first.

    Restricted to Admin and Auditor roles -- everyone else gets a 403, same
    pattern as the Members/Workflows admin endpoints.
    """
    require_roles(member, OrgRole.ADMIN.value, OrgRole.AUDITOR.value)
    org_id = member["org_id"]
    repository = FirestoreRepository("audit_log")
    records = [record for record in repository.stream() if record.get("org_id") == org_id]
    if action:
        records = [record for record in records if record.get("action") == action]
    if resource_type:
        records = [record for record in records if record.get("resource_type") == resource_type]
    records.sort(key=lambda record: record.get("created_at") or "", reverse=True)
    return [_response(record) for record in records[:limit]]
