"""Human-approved AI remediation and re-proof endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..domains.compliance.models import AmendmentRequest, AuditTrailEntry
from ..domains.compliance.remediation import RemediationService

router = APIRouter(prefix="/compliance/remediation", tags=["compliance-remediation"])
_service = RemediationService()


class AmendmentProposalRequest(BaseModel):
    event_id: str
    contract_id: str
    affected_clause: str
    current_language: str
    regulatory_requirement: str
    jurisdiction: str
    amendment_reason: str
    finding_id: Optional[str] = None
    version_id: Optional[str] = None
    evidence_id: Optional[str] = None
    evidence_quote: Optional[str] = None
    source_section: Optional[str] = None


class AmendmentApprovalRequest(BaseModel):
    approved: bool
    approved_by: str = Field(..., min_length=1)
    approval_notes: Optional[str] = None
    rejection_reason: Optional[str] = None


@router.post("/proposals", status_code=status.HTTP_201_CREATED)
def create_amendment_proposal(request: AmendmentProposalRequest):
    """Generate AI language for review; generation does not publish anything."""
    return _service.request_amendment(AmendmentRequest(**request.model_dump()))


@router.post("/proposals/{proposal_id}/approval")
def approve_amendment(proposal_id: str, request: AmendmentApprovalRequest):
    """Approve or reject a proposal, with re-analysis and re-proof after approval."""
    try:
        return _service.approve_and_reproof(proposal_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/events/{event_id}/audit", response_model=List[AuditTrailEntry])
def get_remediation_audit(event_id: str):
    """Return the ordered detection-to-proof audit trail."""
    return _service.get_audit_trail(event_id)
