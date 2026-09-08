"""Authenticated persisted redline proposal endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..services.auth import get_current_user
from ..services.redline_proposals import FinalDecisionError, ProposalNotFoundError, ProposalService, PublicationError, RedlineProposalError
from ..repositories.firestore import FirestoreRepository
from ..services.version_analysis import VersionAnalysisService
from ..services.audit import record_audit_event

router = APIRouter(prefix="/contracts", tags=["redline-proposals"])
proposal_router = APIRouter(prefix="/redline-proposals", tags=["redline-proposals"])


class RedlineProposalCreateRequest(BaseModel):
    source_version_id: str
    finding_id: str
    proposed_text: str = ""
    evidence_id: str | None = None


class RedlineProposalUpdateRequest(BaseModel):
    proposed_text: str = Field(default="")


class RedlineReviewRequest(BaseModel):
    decision: str
    comment: str | None = None


class RedlineReviewResponse(BaseModel):
    review_id: str
    proposal_id: str
    contract_id: str
    source_version_id: str
    finding_id: str
    decision: str
    reviewer_id: str
    comment: str | None = None
    created_at: str
    updated_at: str


class RedlinePublicationResponse(BaseModel):
    proposal_id: str
    status: str
    source_version_id: str
    published_version_id: str
    published_by: str
    published_at: str
    analysis_status: str | None = None


class RedlineProposalResponse(BaseModel):
    proposal_id: str
    contract_id: str
    source_version_id: str
    finding_id: str
    evidence_id: str | None = None
    title: str | None = None
    severity: str | None = None
    original_text: str
    evidence: Any = None
    proposed_text: str
    recommendation: str | None = None
    reason: str | None = None
    status: str
    created_by: str
    created_at: str
    updated_at: str
    review: RedlineReviewResponse | None = None
    published_version_id: str | None = None
    published_by: str | None = None
    published_at: str | None = None
    analysis_status: str | None = None
    workflow_instance_id: str | None = None
    org_id: str | None = None


def _service() -> ProposalService:
    contracts = FirestoreRepository("contracts")
    versions = FirestoreRepository("contract_versions")
    analysis_service = VersionAnalysisService(
        contracts=contracts,
        versions=versions,
    )
    return ProposalService(
        contracts=contracts,
        versions=versions,
        analysis_service=analysis_service,
    )


def _handle_error(error: RedlineProposalError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def _handle_review_error(error: RedlineProposalError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.post("/{contract_id}/redline-proposals", response_model=RedlineProposalResponse, status_code=status.HTTP_201_CREATED)
def create_redline_proposal(
    contract_id: str,
    request: RedlineProposalCreateRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        return _service().create(
            contract_id,
            request.source_version_id,
            request.finding_id,
            request.proposed_text,
            str(user["uid"]),
            request.evidence_id,
        )
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except RedlineProposalError as error:
        raise _handle_error(error) from error


@router.get("/{contract_id}/redline-proposals", response_model=list[RedlineProposalResponse])
def list_redline_proposals(
    contract_id: str,
    version_id: str | None = Query(None),
    finding_id: str | None = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        return _service().list(contract_id, str(user["uid"]), version_id, finding_id)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except RedlineProposalError as error:
        raise _handle_error(error) from error


@proposal_router.patch("/{proposal_id}", response_model=RedlineProposalResponse)
def update_redline_proposal(
    proposal_id: str,
    request: RedlineProposalUpdateRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        return _service().update(proposal_id, request.proposed_text, str(user["uid"]))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ProposalNotFoundError as error:
        raise _handle_error(error) from error


@proposal_router.get("/{proposal_id}", response_model=RedlineProposalResponse)
def get_redline_proposal(proposal_id: str, user: dict[str, Any] = Depends(get_current_user)):
    try:
        return _service().get(proposal_id, str(user["uid"]))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ProposalNotFoundError as error:
        raise _handle_error(error) from error


@proposal_router.post("/{proposal_id}/review", response_model=RedlineReviewResponse)
def review_redline_proposal(
    proposal_id: str,
    request: RedlineReviewRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        result = _service().review(proposal_id, request.decision, str(user["uid"]), request.comment)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except FinalDecisionError as error:
        raise _handle_review_error(error) from error
    except (ProposalNotFoundError, RedlineProposalError) as error:
        raise _handle_error(error) from error
    proposal = _service().proposals.get(proposal_id)
    record_audit_event(
        actor_id=str(user["uid"]),
        actor_email=user.get("email"),
        action=f"redline.{result['decision'].lower()}",
        resource_type="redline_proposal",
        resource_id=proposal_id,
        resource_name=f"Finding {result.get('finding_id', '')}",
        summary=f"{result['decision'].title()} redline proposal for contract {result.get('contract_id', '')}",
        org_id=(proposal or {}).get("org_id"),
    )
    return result


@proposal_router.post("/{proposal_id}/publish", response_model=RedlinePublicationResponse)
def publish_redline_proposal(
    proposal_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        result = _service().publish(proposal_id, str(user["uid"]))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ProposalNotFoundError as error:
        raise _handle_error(error) from error
    except PublicationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    proposal = _service().proposals.get(proposal_id)
    record_audit_event(
        actor_id=str(user["uid"]),
        actor_email=user.get("email"),
        action="redline.published",
        resource_type="redline_proposal",
        resource_id=proposal_id,
        resource_name=f"Published version {result.get('published_version_id', '')}",
        summary=f"Published redline for contract {result.get('source_version_id', '')}",
        org_id=(proposal or {}).get("org_id"),
    )
    return result