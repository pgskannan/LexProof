"""AI-blind human benchmark review endpoints.

This router intentionally exposes only dataset members, contract source text,
and human-entered ground truth. Production findings and evaluator outputs are
not queried here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..repositories.firestore import FirestoreRepository
from ..services.analysis_prompt import ANALYSIS_PROMPT_VERSION
from ..services.auth import get_current_org_member_from_header, get_current_user
from ..services.benchmark_runner import BenchmarkRunService
from ..services.evaluation import (
    EvaluationError,
    EvaluationNotFoundError,
    EvaluationPermissionError,
    EvaluationService,
    EvaluationStatus,
    FindingSeverity,
)
from ..services.organizations import get_organization_service
from ..services.roles import OrgRole, has_any_role

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


class GroundTruthCreateRequest(BaseModel):
    contract_id: str
    version_id: str
    finding_category: str = Field(min_length=1)
    clause_reference: str = Field(min_length=1)
    expected_severity: FindingSeverity
    expected_finding: str = Field(min_length=1)
    expected_evidence: str = Field(min_length=1)
    expected_recommendation: str | None = None


class GroundTruthUpdateRequest(BaseModel):
    finding_category: str | None = None
    clause_reference: str | None = None
    expected_severity: FindingSeverity | None = None
    expected_finding: str | None = None
    expected_evidence: str | None = None
    expected_recommendation: str | None = None
    reviewer_id: str | None = None


class AssignmentRequest(BaseModel):
    reviewer_id: str


class StatusRequest(BaseModel):
    status: EvaluationStatus


class BenchmarkRunRequest(BaseModel):
    """Input for an isolated benchmark run over a finalized dataset."""

    dataset_version_id: str
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    prompt_version: str = ANALYSIS_PROMPT_VERSION
    idempotency_key: str | None = None
    evaluate: bool = True


def _service() -> EvaluationService:
    return EvaluationService()


def _runner() -> BenchmarkRunService:
    return BenchmarkRunService()


def _require_benchmark_roles(member: dict[str, Any], *roles: str, detail: str) -> None:
    if not has_any_role(list(member.get("roles") or []), roles):
        raise HTTPException(status_code=403, detail=detail)


def _raise(exc: Exception) -> None:
    if isinstance(exc, EvaluationNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, EvaluationPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, EvaluationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/benchmarks")
def list_benchmarks(member: dict[str, Any] = Depends(get_current_org_member_from_header)):
    service = _service()
    if not has_any_role(list(member.get("roles") or []), (OrgRole.ADMIN.value, OrgRole.REVIEWER.value, OrgRole.AUDITOR.value)):
        raise HTTPException(status_code=403, detail="Benchmark review access requires an authorized organization role")
    return [
        dataset
        for dataset in service.datasets.stream()
        if dataset.get("org_id") == member.get("org_id") and dataset.get("review_type") == "INTERNAL_REVIEW"
    ]


def _load_many(repository: Any, document_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Look up many documents in as few round trips as the repository allows."""
    get_many = getattr(repository, "get_many", None)
    if callable(get_many):
        return get_many(document_ids)
    return {document_id: repository.get(document_id) for document_id in dict.fromkeys(document_ids)}


@router.get("/benchmarks/{dataset_version_id}/workspace")
def benchmark_workspace(
    dataset_version_id: str,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    service = _service()
    try:
        payload = service.get_review_workspace_payload(member, dataset_version_id)
    except Exception as exc:
        _raise(exc)
        raise

    # Batched reads: this used to call contracts.get()/versions.get() once per
    # contract row (a 2N round-trip N+1). get_many() collapses that to one
    # round trip per 30 ids for each collection.
    rows = payload["contract_rows"]
    contract_map = _load_many(service.contracts, [row["contract_id"] for row in rows])
    version_map = _load_many(service.versions, [row["version_id"] for row in rows])
    enriched_rows = []
    for row in rows:
        contract = contract_map.get(row["contract_id"]) or {}
        version = version_map.get(row["version_id"]) or {}
        enriched_rows.append({
            **row,
            "contract_name": contract.get("name") or contract.get("filename") or row["contract_id"],
            "version_number": version.get("version_number"),
            "document_text": version.get("document_text") or "",
            "assigned_reviewer_id": next(
                (
                    finding.get("reviewer_id")
                    for finding in payload["ground_truth_findings"]
                    if finding.get("contract_id") == row["contract_id"] and finding.get("reviewer_id")
                ),
                payload["dataset"].get("reviewer_id"),
            ),
        })
    payload["contract_rows"] = enriched_rows
    return payload


@router.post("/benchmarks/{dataset_version_id}/finalize")
def finalize_benchmark_dataset(
    dataset_version_id: str,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    """Freeze a benchmark dataset so its ground truth can be evaluated (admin only).

    Uses the existing ``EvaluationService.finalize_dataset`` (all findings must be
    FINALIZED, dataset becomes immutable). Idempotent: finalizing an already
    finalized dataset returns it with ``already_finalized: true`` instead of
    failing. No evaluation run is created here.
    """
    _require_benchmark_roles(
        member,
        OrgRole.ADMIN.value,
        detail="Finalizing a benchmark dataset requires an administrator role",
    )
    service = _service()
    try:
        dataset = service.get_dataset(member, dataset_version_id)
    except Exception as exc:
        _raise(exc)
        raise
    if dataset.get("status") == EvaluationStatus.FINALIZED.value:
        return {
            "dataset_version_id": dataset_version_id,
            "status": dataset.get("status"),
            "finalized_at": dataset.get("finalized_at"),
            "member_count": len(service.members.query(equal={"dataset_version_id": dataset_version_id})),
            "already_finalized": True,
        }
    runner = _runner()
    try:
        # Validates every member's contract/version relationship and document text
        # before the dataset is frozen.
        _, members = runner.dataset_members(member, dataset_version_id)
        finalized = service.finalize_dataset(member, dataset_version_id)
    except Exception as exc:
        _raise(exc)
        raise
    return {**finalized, "member_count": len(members), "already_finalized": False}


@router.post("/runs", status_code=201)
async def create_benchmark_run(
    request: BenchmarkRunRequest,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    """Run LexProof AI over the frozen benchmark versions and score the result.

    Isolated: writes evaluation-run records only (no production findings,
    passports, evidence, anchors or notifications). Re-using the same idempotency
    key returns the existing run instead of creating an equivalent duplicate.
    """
    _require_benchmark_roles(
        member,
        OrgRole.ADMIN.value,
        OrgRole.REVIEWER.value,
        detail="Benchmark execution requires an authorized organization role",
    )
    runner = _runner()
    try:
        result = await runner.start_run(
            member,
            dataset_version_id=request.dataset_version_id,
            provider=request.provider,
            model=request.model,
            model_version=request.model_version,
            prompt_version=request.prompt_version,
            idempotency_key=request.idempotency_key,
            evaluate_after=request.evaluate,
        )
        report = runner.run_report(member, result["run"]["evaluation_run_id"])
    except Exception as exc:
        _raise(exc)
        raise
    return {**report, "reused": result["reused"]}


@router.get("/runs/{evaluation_run_id}")
def get_benchmark_run(
    evaluation_run_id: str,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    """Run status, provenance and metrics. Never returns ground-truth content."""
    _require_benchmark_roles(
        member,
        OrgRole.ADMIN.value,
        OrgRole.REVIEWER.value,
        detail="Benchmark results require an authorized organization role",
    )
    try:
        return _runner().run_report(member, evaluation_run_id)
    except Exception as exc:
        _raise(exc)
        raise


@router.post("/runs/{evaluation_run_id}/evaluate")
async def evaluate_benchmark_run(
    evaluation_run_id: str,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    """Score an existing run with the deterministic evaluator (no new matching logic)."""
    _require_benchmark_roles(
        member,
        OrgRole.ADMIN.value,
        OrgRole.REVIEWER.value,
        detail="Benchmark evaluation requires an authorized organization role",
    )
    runner = _runner()
    try:
        await runner.evaluate_run(member, evaluation_run_id)
        return runner.run_report(member, evaluation_run_id)
    except Exception as exc:
        _raise(exc)
        raise


@router.get("/benchmarks/{dataset_version_id}/reviewers")
def benchmark_reviewers(
    dataset_version_id: str,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    service = _service()
    try:
        dataset = service.get_dataset(member, dataset_version_id)
    except Exception as exc:
        _raise(exc)
        raise
    reviewers = []
    for candidate in get_organization_service().list_members(str(dataset["org_id"])):
        if candidate.get("status") != "active":
            continue
        roles = list(candidate.get("roles") or [])
        if has_any_role(roles, (OrgRole.ADMIN.value, OrgRole.REVIEWER.value)):
            reviewers.append({
                "user_id": candidate.get("user_id"),
                "display_name": candidate.get("display_name") or candidate.get("email") or candidate.get("user_id"),
                "email": candidate.get("email"),
                "roles": roles,
            })
    return reviewers


@router.post("/benchmarks/{dataset_version_id}/findings", status_code=201)
def create_benchmark_finding(
    dataset_version_id: str,
    request: GroundTruthCreateRequest,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    try:
        return _service().create_ground_truth(member, dataset_version_id=dataset_version_id, **request.model_dump(mode="json"))
    except Exception as exc:
        _raise(exc)
        raise


@router.patch("/benchmarks/{dataset_version_id}/findings/{ground_truth_id}")
def update_benchmark_finding(
    dataset_version_id: str,
    ground_truth_id: str,
    request: GroundTruthUpdateRequest,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    try:
        finding = _service().ground_truth.get(ground_truth_id)
        if not finding or finding.get("dataset_version_id") != dataset_version_id:
            raise EvaluationNotFoundError(f"Ground-truth finding not found: {ground_truth_id}")
        return _service().update_ground_truth(member, ground_truth_id, **request.model_dump(mode="json", exclude_none=True))
    except Exception as exc:
        _raise(exc)
        raise


@router.post("/benchmarks/{dataset_version_id}/findings/{ground_truth_id}/assign")
def assign_benchmark_finding(
    dataset_version_id: str,
    ground_truth_id: str,
    request: AssignmentRequest,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    try:
        finding = _service().ground_truth.get(ground_truth_id)
        if not finding or finding.get("dataset_version_id") != dataset_version_id:
            raise EvaluationNotFoundError(f"Ground-truth finding not found: {ground_truth_id}")
        return _service().assign_ground_truth(member, ground_truth_id, request.reviewer_id)
    except Exception as exc:
        _raise(exc)
        raise


@router.post("/benchmarks/{dataset_version_id}/findings/{ground_truth_id}/status")
def transition_benchmark_finding(
    dataset_version_id: str,
    ground_truth_id: str,
    request: StatusRequest,
    member: dict[str, Any] = Depends(get_current_org_member_from_header),
):
    try:
        finding = _service().ground_truth.get(ground_truth_id)
        if not finding or finding.get("dataset_version_id") != dataset_version_id:
            raise EvaluationNotFoundError(f"Ground-truth finding not found: {ground_truth_id}")
        return _service().transition_ground_truth(member, ground_truth_id, request.status)
    except Exception as exc:
        _raise(exc)
        raise
