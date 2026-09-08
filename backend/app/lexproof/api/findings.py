"""Authenticated retrieval of persisted AI contract findings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_user

router = APIRouter(prefix="/findings", tags=["findings"])


class FindingResponse(BaseModel):
    finding_id: str
    contract_id: Optional[str] = None
    version_id: Optional[str] = None
    title: str = ""
    severity: Optional[str] = None
    description: str = ""
    risk_impact: Optional[float] = None
    compliance_impact: Optional[float] = None
    evidence: Any = None
    evidence_quote: Optional[str] = None
    source_section: Optional[str] = None
    recommendation: Optional[str] = None
    created_at: Optional[datetime] = None


def _visible(record: dict[str, Any], uid: str) -> bool:
    owner_id = record.get("owner_id")
    return not owner_id or owner_id == uid


def _response(record: dict[str, Any]) -> FindingResponse:
    return FindingResponse(
        finding_id=str(record.get("finding_id") or record.get("id") or ""),
        contract_id=record.get("contract_id"),
        version_id=record.get("version_id"),
        title=str(record.get("title") or ""),
        severity=record.get("severity"),
        description=str(record.get("description") or ""),
        risk_impact=record.get("risk_impact"),
        compliance_impact=record.get("compliance_impact"),
        evidence=record.get("evidence"),
        evidence_quote=record.get("evidence_quote"),
        source_section=record.get("source_section"),
        recommendation=record.get("recommendation"),
        created_at=record.get("created_at"),
    )


@router.get("", response_model=list[FindingResponse])
def list_findings(
    contract_id: Optional[str] = Query(None),
    version_id: Optional[str] = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[FindingResponse]:
    """Return persisted findings visible to the authenticated user."""
    uid = str(user["uid"])
    repository = FirestoreRepository("risk_findings")
    records = (
        record for record in repository.stream()
        if _visible(record, uid)
        and (contract_id is None or record.get("contract_id") == contract_id)
        and (version_id is None or record.get("version_id") == version_id)
    )
    return [_response(record) for record in records]