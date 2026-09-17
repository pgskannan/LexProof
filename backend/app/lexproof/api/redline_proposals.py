"""Authenticated persisted redline proposal endpoints."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..services.auth import get_current_user
from ..services.redline_proposals import FinalDecisionError, ProposalNotFoundError, ProposalService, PublicationError, RedlineProposalError
from ..services.redline_suggestions import RedlineSuggestionError, RedlineSuggestionService, get_redline_suggestion_service
from ..services.vertex_ai import VertexAIError
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


class RedlineSuggestionRequest(BaseModel):
    finding_id: str


class RedlineSuggestionResponse(BaseModel):
    suggested_text: str
    rationale: str
    original_text: str
    clause_type: str | None = None
    playbook_standard_position: str | None = None


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
    contract_id: str
    status: str
    source_version_id: str
    published_version_id: str
    published_by: str
    published_at: str
    analysis_status: str | None = None
    publication_status: str | None = None
    passport_status: str | None = None
    evidence_count: int = 0
    anchored_evidence_count: int = 0
    proof_status: str = "action_required"
    recommended_action: str = "retry"


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
    sla_due_at: str | None = None
    is_overdue: bool = False
    publication_status: str | None = None
    passport_status: str | None = None
    evidence_count: int = 0
    anchored_evidence_count: int = 0
    proof_status: str = "action_required"
    recommended_action: str = "retry"


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


def _suggestion_service() -> RedlineSuggestionService:
    return get_redline_suggestion_service()


def _handle_error(error: RedlineProposalError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def _handle_review_error(error: RedlineProposalError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.post("/{contract_id}/redline-proposals/suggest", response_model=RedlineSuggestionResponse)
async def suggest_redline_language(
    contract_id: str,
    request: RedlineSuggestionRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    """AI-drafted starting point for a redline: never persisted, never a proposal --
    the caller must still review, edit if needed, and explicitly save it."""
    try:
        return await _suggestion_service().suggest(contract_id, request.finding_id, str(user["uid"]))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except RedlineSuggestionError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except VertexAIError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.post("/{contract_id}/redline-proposals", response_model=RedlineProposalResponse, status_code=status.HTTP_201_CREATED)
def create_redline_proposal(
    contract_id: str,
    request: RedlineProposalCreateRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        result = _service().create(
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
    record_audit_event(
        actor_id=str(user["uid"]),
        actor_email=user.get("email"),
        action="redline.created",
        resource_type="redline_proposal",
        resource_id=result.get("proposal_id"),
        resource_name=f"Finding {result.get('finding_id', '')}",
        contract_id=result.get("contract_id"),
        summary=f"Created redline proposal for contract {result.get('contract_id', '')}",
        org_id=result.get("org_id"),
        metadata={"finding_id": result.get("finding_id"), "source_version_id": result.get("source_version_id")},
    )
    return result


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
        contract_id=result.get("contract_id"),
        summary=f"{result['decision'].title()} redline proposal for contract {result.get('contract_id', '')}",
        org_id=(proposal or {}).get("org_id"),
        metadata={
            "comment": result.get("comment"),
            "workflow_instance_id": (proposal or {}).get("workflow_instance_id"),
            "actor_roles": result.get("reviewer_roles"),
        },
    )
    return result


@proposal_router.post("/{proposal_id}/publish", response_model=RedlinePublicationResponse)
def publish_redline_proposal(
    proposal_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, Any] = Depends(get_current_user),
):
    service = _service()
    try:
        result = service.publish(proposal_id, str(user["uid"]))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ProposalNotFoundError as error:
        raise _handle_error(error) from error
    except PublicationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    proposal = service.proposals.get(proposal_id)
    # The publish itself is already fully committed above (new version created,
    # proposal marked PUBLISHED, publication audit recorded) -- this response is
    # about to return successfully regardless of what happens next. Gemini
    # analysis + Ethereum evidence anchoring for the new version are slow and
    # best-effort, so they run as a background task *after* the response is
    # sent rather than blocking this request on them (see ProposalService.
    # publish()/run_post_publish_analysis() for the full rationale -- hardening
    # item #1, publish success/error semantic separation). Scheduling on
    # "failed" too means a retried/idempotent publish call naturally retries a
    # previously failed analysis run; "complete" and "not_attempted" (no
    # analysis service configured) schedule nothing.
    if result.get("analysis_status") in ("pending", "failed") and result.get("published_version_id"):
        background_tasks.add_task(
            service.run_post_publish_analysis,
            proposal_id,
            (proposal or {}).get("contract_id"),
            result["published_version_id"],
            str(user["uid"]),
        )
    record_audit_event(
        actor_id=str(user["uid"]),
        actor_email=user.get("email"),
        action="redline.published",
        resource_type="redline_proposal",
        resource_id=proposal_id,
        resource_name=f"Published version {result.get('published_version_id', '')}",
        contract_id=result.get("contract_id"),
        summary=f"Published redline for contract {result.get('contract_id', '')}",
        org_id=(proposal or {}).get("org_id"),
    )
    return result