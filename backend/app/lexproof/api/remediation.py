"""Human-approved AI remediation and re-proof endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..domains.compliance.models import AmendmentRequest, AuditTrailEntry
from ..domains.compliance.remediation import RemediationService
from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_user

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
def create_amendment_proposal(request: AmendmentProposalRequest, user: dict = Depends(get_current_user)):
    """Generate AI language for review; generation does not publish anything."""
    contract = FirestoreRepository("contracts").get(request.contract_id)
    if not contract or contract.get("owner_id") != str(user["uid"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return _service.request_amendment(
        AmendmentRequest(**request.model_dump()),
        created_by=str(user["uid"]),
        org_id=contract.get("org_id"),
    )


@router.post("/proposals/{proposal_id}/approval")
def approve_amendment(proposal_id: str, request: AmendmentApprovalRequest, user: dict = Depends(get_current_user)):
    """Approve or reject a proposal, with re-analysis and re-proof after approval."""
    try:
        if request.approved_by != str(user["uid"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approved_by must match the authenticated user")
        return _service.approve_and_reproof(
            proposal_id,
            approved=request.approved,
            approved_by=str(user["uid"]),
            approval_notes=request.approval_notes,
            rejection_reason=request.rejection_reason,
            approver_id=str(user["uid"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/events/{event_id}/audit", response_model=List[AuditTrailEntry])
def get_remediation_audit(event_id: str):
    """Return the ordered detection-to-proof audit trail."""
    return _service.get_audit_trail(event_id)
