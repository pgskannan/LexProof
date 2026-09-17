"""Isolated, organization-scoped AI evaluation data model.

This module intentionally does not invoke production analysis or write any
production analysis collections. Evaluation outputs live in their own
collections and reference immutable contract/version identifiers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..repositories.firestore import FirestoreRepository
from .organizations import OrganizationService, get_organization_service
from .roles import OrgRole, has_any_role
from .audit import record_audit_event


class EvaluationError(ValueError):
    """Base error for evaluation data validation failures."""


class EvaluationPermissionError(PermissionError):
    """Raised when a member lacks evaluation access."""


class EvaluationNotFoundError(EvaluationError):
    """Raised when an evaluation record does not exist."""


class EvaluationStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    FINALIZED = "FINALIZED"


class EvaluationRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class EvaluationMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    MISSED = "MISSED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    UNCERTAIN = "UNCERTAIN"


class FindingSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvaluationReviewType(str, Enum):
    INTERNAL_REVIEW = "INTERNAL_REVIEW"
    INDEPENDENT_REVIEW = "INDEPENDENT_REVIEW"


class GroundTruthSource(str, Enum):
    INTERNAL_HUMAN_REVIEW = "INTERNAL_HUMAN_REVIEW"
    INDEPENDENT_LEGAL_REVIEW = "INDEPENDENT_LEGAL_REVIEW"


class EvaluationRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class EvaluationDataset(EvaluationRecord):
    dataset_version_id: str
    org_id: str
    name: str
    description: str = ""
    version_label: str
    status: EvaluationStatus = EvaluationStatus.DRAFT
    contract_count: int = Field(default=0, ge=0)
    ground_truth_finding_count: int = Field(default=0, ge=0)
    created_by: str
    created_at: datetime
    finalized_at: datetime | None = None
    classification: EvaluationReviewType = EvaluationReviewType.INTERNAL_REVIEW
    review_type: EvaluationReviewType = EvaluationReviewType.INTERNAL_REVIEW
    reviewer_type: str = "INTERNAL_REVIEWER"
    reviewer_id: str | None = None
    review_started_at: datetime | None = None
    review_completed_at: datetime | None = None
    ai_blind: bool = True
    ground_truth_source: GroundTruthSource = GroundTruthSource.INTERNAL_HUMAN_REVIEW


class EvaluationDatasetMember(EvaluationRecord):
    dataset_member_id: str
    org_id: str
    dataset_version_id: str
    contract_id: str
    version_id: str
    added_by: str
    added_at: datetime


class EvaluationGroundTruthFinding(EvaluationRecord):
    ground_truth_id: str
    org_id: str
    dataset_version_id: str
    contract_id: str
    version_id: str
    finding_category: str
    clause_reference: str
    expected_severity: FindingSeverity
    expected_finding: str
    expected_evidence: str
    expected_recommendation: str | None = None
    reviewer_id: str
    review_status: EvaluationStatus = EvaluationStatus.DRAFT
    created_at: datetime
    finalized_at: datetime | None = None
    supersedes_id: str | None = None


class EvaluationRun(EvaluationRecord):
    evaluation_run_id: str
    org_id: str
    dataset_version_id: str
    provider: str
    model: str
    model_version: str | None = None
    prompt_version: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    contract_count: int = Field(default=0, ge=0)
    ground_truth_count: int = Field(default=0, ge=0)
    ai_finding_count: int = Field(default=0, ge=0)
    status: EvaluationRunStatus = EvaluationRunStatus.PENDING
    error_summary: str | None = None
    created_by: str
    evaluator_version: str | None = None
    # Exact benchmark inputs for this run: one entry per dataset member with the
    # frozen contract/version ids and the content hash that was analysed. Stored
    # so a result can always be explained without re-reading mutable sources.
    dataset_members: list[dict[str, Any]] = Field(default_factory=list)
    # Deterministic run identity: the same dataset + provider + model + prompt
    # version + key must never produce a second equivalent run.
    idempotency_key: str | None = None
    failed_contract_ids: list[str] = Field(default_factory=list)
    contract_errors: dict[str, str] = Field(default_factory=dict)
    # Non-fatal mapping notes (for example an AI severity outside the evaluation
    # scale, which is recorded rather than invented).
    contract_warnings: dict[str, list[str]] = Field(default_factory=dict)
    evaluated_at: datetime | None = None


class EvaluationRunFinding(EvaluationRecord):
    evaluation_finding_id: str
    org_id: str
    evaluation_run_id: str
    dataset_version_id: str
    contract_id: str
    version_id: str
    finding_category: str
    clause_reference: str
    severity: FindingSeverity
    finding: str
    evidence: str
    recommendation: str | None = None
    provider: str
    model: str
    created_at: datetime


class EvaluationMatch(EvaluationRecord):
    evaluation_match_id: str
    org_id: str
    evaluation_run_id: str
    ground_truth_id: str | None = None
    evaluation_finding_id: str | None = None
    contract_id: str
    version_id: str
    status: EvaluationMatchStatus
    category_match: bool | None = None
    clause_match: bool | None = None
    evidence_match: bool | None = None
    numeric_match: bool | None = None
    severity_match: bool | None = None
    severity_correct: bool | None = None
    expected_severity: FindingSeverity | None = None
    ai_severity: FindingSeverity | None = None
    evidence_grounding: str = "UNKNOWN"
    recommendation_correct: bool | None = None
    match_score: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    match_reason: str = ""
    rationale: str = ""
    evaluator_version: str = "1.0.0"
    adjudicated_by: str | None = None
    adjudicated_at: datetime | None = None
    created_at: datetime


class EvaluationMetrics(EvaluationRecord):
    evaluation_metrics_id: str
    org_id: str
    evaluation_run_id: str
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1: float | None = Field(default=None, ge=0, le=1)
    severity_accuracy: float | None = Field(default=None, ge=0, le=1)
    critical_recall: float | None = Field(default=None, ge=0, le=1)
    high_risk_recall: float | None = Field(default=None, ge=0, le=1)
    evidence_grounding: float | None = Field(default=None, ge=0, le=1)
    recommendation_accuracy: float | None = Field(default=None, ge=0, le=1)
    true_positives: int = Field(default=0, ge=0)
    false_positives: int = Field(default=0, ge=0)
    false_negatives: int = Field(default=0, ge=0)
    uncertain_count: int = Field(default=0, ge=0)
    calculated_at: datetime
    evaluator_version: str = "1.0.0"


class FinalizedGroundTruthRepository(FirestoreRepository):
    """Repository guard preventing mutation of finalized ground truth."""

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False, transaction: Any | None = None) -> None:
        existing = self.get(document_id)
        if existing and existing.get("review_status") == EvaluationStatus.FINALIZED.value:
            raise EvaluationError("Finalized ground-truth findings are immutable")
        super().set(document_id, data, merge=merge, transaction=transaction)

    def delete(self, document_id: str) -> None:
        existing = self.get(document_id)
        if existing and existing.get("review_status") == EvaluationStatus.FINALIZED.value:
            raise EvaluationError("Finalized ground-truth findings are immutable")
        super().delete(document_id)


class EvaluationService:
    """Repository-backed lifecycle for isolated evaluation records."""

    COLLECTIONS = {
        "datasets": "evaluation_datasets",
        "members": "evaluation_dataset_members",
        "ground_truth": "evaluation_ground_truth_findings",
        "runs": "evaluation_runs",
        "run_findings": "evaluation_run_findings",
        "matches": "evaluation_matches",
        "metrics": "evaluation_metrics",
    }

    def __init__(
        self,
        *,
        organizations: OrganizationService | None = None,
        datasets: FirestoreRepository | None = None,
        members: FirestoreRepository | None = None,
        ground_truth: FirestoreRepository | None = None,
        runs: FirestoreRepository | None = None,
        run_findings: FirestoreRepository | None = None,
        matches: FirestoreRepository | None = None,
        metrics: FirestoreRepository | None = None,
        contracts: FirestoreRepository | None = None,
        versions: FirestoreRepository | None = None,
        audit_recorder: Any | None = None,
    ) -> None:
        self.organizations = organizations or get_organization_service()
        self.datasets = datasets or FirestoreRepository(self.COLLECTIONS["datasets"])
        self.members = members or FirestoreRepository(self.COLLECTIONS["members"])
        self.ground_truth = ground_truth or FinalizedGroundTruthRepository(self.COLLECTIONS["ground_truth"])
        self.runs = runs or FirestoreRepository(self.COLLECTIONS["runs"])
        self.run_findings = run_findings or FirestoreRepository(self.COLLECTIONS["run_findings"])
        self.matches = matches or FirestoreRepository(self.COLLECTIONS["matches"])
        self.metrics = metrics or FirestoreRepository(self.COLLECTIONS["metrics"])
        self.contracts = contracts or FirestoreRepository("contracts")
        self.versions = versions or FirestoreRepository("contract_versions")
        self.audit_recorder = audit_recorder

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _uid(member: dict[str, Any]) -> str:
        return str(member.get("uid") or "")

    @classmethod
    def _require_org_role(cls, member: dict[str, Any], org_id: str, *roles: str) -> str:
        if str(member.get("org_id") or "") != org_id:
            raise EvaluationPermissionError("You are not an active member of this organization")
        held = list(member.get("roles") or [])
        if not has_any_role(held, roles):
            raise EvaluationPermissionError("You are not authorized to access evaluation data")
        uid = cls._uid(member)
        if not uid:
            raise EvaluationPermissionError("Evaluation access requires an authenticated member")
        return uid

    def _dataset(self, dataset_version_id: str, member: dict[str, Any], *roles: str) -> dict[str, Any]:
        dataset = self.datasets.get(dataset_version_id)
        if not dataset:
            raise EvaluationNotFoundError(f"Evaluation dataset not found: {dataset_version_id}")
        self._require_org_role(member, str(dataset.get("org_id") or ""), *roles)
        return dataset

    def _org_membership(self, org_id: str, user_id: str) -> dict[str, Any] | None:
        return self.organizations.get_active_member(org_id, user_id)

    def _can_assign_reviewer(self, org_id: str, reviewer_user_id: str) -> bool:
        member = self._org_membership(org_id, reviewer_user_id)
        if not member:
            return False
        roles = list(member.get("roles") or [])
        return has_any_role(roles, (OrgRole.ADMIN.value, OrgRole.REVIEWER.value))

    def _ensure_dataset_open(self, dataset: dict[str, Any]) -> None:
        if dataset.get("status") == EvaluationStatus.FINALIZED.value:
            raise EvaluationError("Finalized evaluation datasets are immutable")

    def _audit(self, *, member: dict[str, Any], action: str, dataset: dict[str, Any], contract_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        if not self.audit_recorder:
            return
        self.audit_recorder(
            actor_id=self._uid(member),
            actor_email=member.get("email"),
            action=action,
            resource_type="evaluation_dataset",
            resource_id=dataset.get("dataset_version_id"),
            resource_name=dataset.get("name"),
            contract_id=contract_id,
            org_id=dataset.get("org_id"),
            summary=f"{action} for evaluation dataset {dataset.get('dataset_version_id')}",
            metadata={"review_type": dataset.get("review_type"), **(metadata or {})},
        )

    def get_dataset(self, member: dict[str, Any], dataset_version_id: str) -> dict[str, Any]:
        return self._dataset(
            dataset_version_id,
            member,
            OrgRole.ADMIN.value,
            OrgRole.REVIEWER.value,
            OrgRole.AUDITOR.value,
        )

    def create_dataset(self, member: dict[str, Any], *, name: str, description: str, version_label: str, review_type: EvaluationReviewType = EvaluationReviewType.INTERNAL_REVIEW, reviewer_type: str = "INTERNAL_REVIEWER", reviewer_id: str | None = None, ai_blind: bool = True, ground_truth_source: GroundTruthSource = GroundTruthSource.INTERNAL_HUMAN_REVIEW) -> dict[str, Any]:
        org_id = str(member.get("org_id") or "")
        uid = self._require_org_role(member, org_id, OrgRole.ADMIN.value)
        if review_type == EvaluationReviewType.INDEPENDENT_REVIEW and (
            not reviewer_id
            or reviewer_type == "INTERNAL_REVIEWER"
            or ground_truth_source != GroundTruthSource.INDEPENDENT_LEGAL_REVIEW
        ):
            raise EvaluationError("Independent review datasets require explicit independent reviewer metadata")
        record = EvaluationDataset(
            dataset_version_id=str(uuid4()), org_id=org_id, name=name, description=description,
            version_label=version_label, created_by=uid, created_at=self._now(),
            classification=review_type, review_type=review_type, reviewer_type=reviewer_type,
            reviewer_id=reviewer_id, ai_blind=ai_blind, ground_truth_source=ground_truth_source,
        )
        self.datasets.set(record.dataset_version_id, record.model_dump(mode="json"))
        self._audit(member=member, action="dataset_created", dataset=record.model_dump(mode="json"))
        return record.model_dump(mode="json")

    def add_dataset_member(self, member: dict[str, Any], *, dataset_version_id: str, contract_id: str, version_id: str) -> dict[str, Any]:
        dataset = self._dataset(dataset_version_id, member, OrgRole.ADMIN.value)
        self._ensure_dataset_open(dataset)
        contract = self.contracts.get(contract_id)
        version = self.versions.get(version_id)
        if not contract or str(contract.get("id") or contract.get("contract_id")) != contract_id:
            raise EvaluationError(f"Contract not found: {contract_id}")
        if not version or version.get("contract_id") != contract_id:
            raise EvaluationError(f"Contract version not found: {version_id}")
        if any(row.get("dataset_version_id") == dataset_version_id and row.get("version_id") == version_id for row in self.members.stream()):
            raise EvaluationError("Contract version is already in this evaluation dataset")
        record = EvaluationDatasetMember(
            dataset_member_id=str(uuid4()), org_id=dataset["org_id"], dataset_version_id=dataset_version_id,
            contract_id=contract_id, version_id=version_id, added_by=self._uid(member), added_at=self._now(),
        )
        self.members.set(record.dataset_member_id, record.model_dump(mode="json"))
        current_dataset = self.datasets.get(dataset_version_id) or dataset
        self.datasets.set(dataset_version_id, {"contract_count": current_dataset.get("contract_count", 0) + 1}, merge=True)
        self._audit(member=member, action="dataset_member_added", dataset=dataset, contract_id=contract_id)
        return record.model_dump(mode="json")

    def finalize_dataset(self, member: dict[str, Any], dataset_version_id: str) -> dict[str, Any]:
        dataset = self._dataset(dataset_version_id, member, OrgRole.ADMIN.value)
        self._ensure_dataset_open(dataset)
        ground_truth = [
            record
            for record in self.ground_truth.stream()
            if record.get("dataset_version_id") == dataset_version_id
        ]
        if any(record.get("review_status") != EvaluationStatus.FINALIZED.value for record in ground_truth):
            raise EvaluationError("All ground-truth findings must be finalized before the dataset is finalized")
        finalized_at = self._now().isoformat()
        updates = {"status": EvaluationStatus.FINALIZED.value, "finalized_at": finalized_at}
        self.datasets.set(dataset_version_id, updates, merge=True)
        self._audit(member=member, action="dataset_finalized", dataset={**dataset, **updates})
        return {**dataset, **updates}

    def create_ground_truth(self, member: dict[str, Any], **fields: Any) -> dict[str, Any]:
        dataset = self._dataset(fields["dataset_version_id"], member, OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        self._ensure_dataset_open(dataset)
        version = self.versions.get(fields["version_id"])
        if not version or version.get("contract_id") != fields["contract_id"]:
            raise EvaluationError("Ground truth version does not belong to the contract")
        record = EvaluationGroundTruthFinding(
            ground_truth_id=str(uuid4()), org_id=dataset["org_id"], reviewer_id=self._uid(member),
            review_status=EvaluationStatus.DRAFT, created_at=self._now(), **fields,
        )
        self.ground_truth.set(record.ground_truth_id, record.model_dump(mode="json"))
        self.datasets.set(dataset["dataset_version_id"], {"ground_truth_finding_count": dataset.get("ground_truth_finding_count", 0) + 1}, merge=True)
        self._audit(member=member, action="ground_truth_created", dataset=dataset, contract_id=fields["contract_id"])
        return record.model_dump(mode="json")

    def list_ground_truth_findings(
        self,
        member: dict[str, Any],
        dataset_version_id: str,
        *,
        contract_id: str | None = None,
        status: EvaluationStatus | str | None = None,
        search: str | None = None,
        reviewer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self._dataset(dataset_version_id, member, OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        return self._filter_findings(
            self.ground_truth.query(equal={"dataset_version_id": dataset_version_id}),
            contract_id=contract_id,
            status=status,
            search=search,
            reviewer_id=reviewer_id,
        )

    @staticmethod
    def _filter_findings(
        records: list[dict[str, Any]],
        *,
        contract_id: str | None = None,
        status: EvaluationStatus | str | None = None,
        search: str | None = None,
        reviewer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Apply the review-workspace filters to already-loaded findings.

        The records are passed in so a caller that has already loaded the
        dataset's findings does not pay for a second read.
        """
        matched = [
            record
            for record in records
            if (contract_id is None or record.get("contract_id") == contract_id)
            and (status is None or record.get("review_status") == str(status.value if isinstance(status, EvaluationStatus) else status))
            and (search is None or search == "" or (record.get("finding_category") or "").lower().find(str(search).lower()) >= 0 or (record.get("clause_reference") or "").lower().find(str(search).lower()) >= 0)
            and (reviewer_id is None or record.get("reviewer_id") == reviewer_id)
        ]
        return sorted(matched, key=lambda item: str(item.get("created_at") or ""))

    def assign_ground_truth(self, member: dict[str, Any], ground_truth_id: str, reviewer_id: str) -> dict[str, Any]:
        record = self.ground_truth.get(ground_truth_id)
        if not record:
            raise EvaluationNotFoundError(f"Ground-truth finding not found: {ground_truth_id}")
        self._require_org_role(member, str(record.get("org_id") or ""), OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        if not self._can_assign_reviewer(str(record.get("org_id") or ""), str(reviewer_id)):
            raise EvaluationPermissionError("Assignee must be an active reviewer or admin in the same organization")

        if str(reviewer_id) == str(member.get("uid") or ""):
            # allow self-assignment within the same org if the user is authorized
            pass

        updates = {"reviewer_id": str(reviewer_id), "review_status": record.get("review_status", EvaluationStatus.DRAFT.value)}
        self.ground_truth.set(ground_truth_id, updates, merge=True)
        dataset = self.datasets.get(record.get("dataset_version_id") or "") or {"dataset_version_id": record.get("dataset_version_id"), "org_id": record.get("org_id")}
        self._audit(member=member, action="ground_truth_assigned", dataset=dataset, contract_id=record.get("contract_id"), metadata={"ground_truth_id": ground_truth_id, "reviewer_id": reviewer_id})
        return {**record, **updates}

    def update_ground_truth(self, member: dict[str, Any], ground_truth_id: str, **fields: Any) -> dict[str, Any]:
        record = self.ground_truth.get(ground_truth_id)
        if not record:
            raise EvaluationNotFoundError(f"Ground-truth finding not found: {ground_truth_id}")
        self._require_org_role(member, str(record.get("org_id") or ""), OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        current_status = EvaluationStatus(record.get("review_status", EvaluationStatus.DRAFT.value))
        if current_status == EvaluationStatus.FINALIZED:
            raise EvaluationError("Finalized ground-truth records are read-only")

        allowed_fields = {
            "finding_category",
            "clause_reference",
            "expected_severity",
            "expected_finding",
            "expected_evidence",
            "expected_recommendation",
            "review_status",
            "reviewer_id",
        }
        updates = {key: value for key, value in fields.items() if key in allowed_fields}
        if updates.get("review_status") is not None:
            next_status = EvaluationStatus(str(updates["review_status"]))
            if next_status == EvaluationStatus.FINALIZED:
                raise EvaluationError("Use transition_ground_truth for finalized status changes")
        if "reviewer_id" in updates and not self._can_assign_reviewer(str(record.get("org_id") or ""), str(updates["reviewer_id"])):
            raise EvaluationPermissionError("Assignee must be an active reviewer or admin in the same organization")
        if "expected_severity" in updates and isinstance(updates["expected_severity"], str):
            updates["expected_severity"] = FindingSeverity(updates["expected_severity"]).value

        self.ground_truth.set(ground_truth_id, updates, merge=True)
        self._audit(member=member, action="ground_truth_updated", dataset=self.datasets.get(record.get("dataset_version_id") or "") or {"dataset_version_id": record.get("dataset_version_id")}, contract_id=record.get("contract_id"), metadata={"ground_truth_id": ground_truth_id, **updates})
        return {**record, **updates}

    def get_review_workspace_payload(
        self,
        member: dict[str, Any],
        dataset_version_id: str,
        *,
        contract_id: str | None = None,
    ) -> dict[str, Any]:
        dataset = self._dataset(dataset_version_id, member, OrgRole.ADMIN.value, OrgRole.REVIEWER.value, OrgRole.AUDITOR.value)
        # The dataset document is already loaded above, so re-derive the
        # findings authorization from it instead of reading the same document a
        # second time (this endpoint used to fetch it twice per request). The
        # role set is deliberately identical to list_ground_truth_findings so
        # access is unchanged.
        self._require_org_role(member, str(dataset.get("org_id") or ""), OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        findings = self._filter_findings(
            self.ground_truth.query(equal={"dataset_version_id": dataset_version_id}),
            contract_id=contract_id,
        )
        contract_rows = []
        # Only this dataset's members are relevant, so ask Firestore for them
        # instead of streaming the whole collection and filtering in Python.
        for row in self.members.query(equal={"dataset_version_id": dataset_version_id}):
            contract_rows.append({
                "contract_id": row.get("contract_id"),
                "version_id": row.get("version_id"),
                "dataset_member_id": row.get("dataset_member_id"),
                # The dataset's own insertion order. Document-id order (what the
                # query above returns) is arbitrary with respect to how the
                # benchmark was assembled, so the reviewer's "next benchmark"
                # progression orders the workspace by this value instead.
                "added_at": row.get("added_at"),
                "finding_count": sum(1 for item in findings if item.get("contract_id") == row.get("contract_id")),
                "reviewed_count": sum(1 for item in findings if item.get("contract_id") == row.get("contract_id") and item.get("review_status") in {EvaluationStatus.IN_REVIEW.value, EvaluationStatus.APPROVED.value, EvaluationStatus.FINALIZED.value}),
            })

        payload = {
            "dataset": dataset,
            "contract_rows": contract_rows,
            "ground_truth_findings": findings,
            "review_progress": {
                "contract_total": len(contract_rows),
                "reviewed_total": sum(1 for item in findings if item.get("review_status") in {EvaluationStatus.IN_REVIEW.value, EvaluationStatus.APPROVED.value, EvaluationStatus.FINALIZED.value}),
                "total_findings": len(findings),
            },
        }
        return payload

    def transition_ground_truth(self, member: dict[str, Any], ground_truth_id: str, status: EvaluationStatus) -> dict[str, Any]:
        record = self.ground_truth.get(ground_truth_id)
        if not record:
            raise EvaluationNotFoundError(f"Ground-truth finding not found: {ground_truth_id}")
        roles = (OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        self._require_org_role(member, str(record.get("org_id") or ""), *roles)
        current = EvaluationStatus(record.get("review_status", EvaluationStatus.DRAFT.value))
        allowed = {
            EvaluationStatus.DRAFT: {EvaluationStatus.IN_REVIEW},
            EvaluationStatus.IN_REVIEW: {EvaluationStatus.APPROVED, EvaluationStatus.DRAFT},
            EvaluationStatus.APPROVED: {EvaluationStatus.FINALIZED},
            EvaluationStatus.FINALIZED: set(),
        }
        if status not in allowed[current]:
            raise EvaluationError(f"Invalid ground-truth transition: {current.value} -> {status.value}")
        updates: dict[str, Any] = {"review_status": status.value, "reviewer_id": self._uid(member)}
        if status == EvaluationStatus.FINALIZED:
            updates["finalized_at"] = self._now().isoformat()
        self.ground_truth.set(ground_truth_id, updates, merge=True)
        action_by_status = {
            EvaluationStatus.IN_REVIEW: "review_started",
            EvaluationStatus.APPROVED: "ground_truth_approved",
            EvaluationStatus.FINALIZED: "ground_truth_finalized",
        }
        dataset = self.datasets.get(record.get("dataset_version_id")) or {"dataset_version_id": record.get("dataset_version_id"), "org_id": record.get("org_id")}
        if status in action_by_status:
            self._audit(member=member, action=action_by_status[status], dataset=dataset, contract_id=record.get("contract_id"), metadata={"ground_truth_id": ground_truth_id})
        return {**record, **updates}

    def supersede_ground_truth(self, member: dict[str, Any], ground_truth_id: str, **fields: Any) -> dict[str, Any]:
        original = self.ground_truth.get(ground_truth_id)
        if not original:
            raise EvaluationNotFoundError(f"Ground-truth finding not found: {ground_truth_id}")
        if original.get("review_status") != EvaluationStatus.FINALIZED.value:
            raise EvaluationError("Only finalized ground truth can be superseded")
        fields = {**original, **fields, "dataset_version_id": original["dataset_version_id"], "contract_id": original["contract_id"], "version_id": original["version_id"], "supersedes_id": ground_truth_id}
        for key in ("ground_truth_id", "review_status", "reviewer_id", "created_at", "finalized_at", "org_id"):
            fields.pop(key, None)
        return self.create_ground_truth(member, **fields)

    def create_run(self, member: dict[str, Any], *, dataset_version_id: str, provider: str, model: str, model_version: str | None = None, prompt_version: str | None = None, evaluator_version: str | None = None, idempotency_key: str | None = None, dataset_members: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        dataset = self._dataset(dataset_version_id, member, OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        if dataset.get("status") != EvaluationStatus.FINALIZED.value:
            raise EvaluationError("Evaluation runs require a finalized dataset")
        record = EvaluationRun(
            evaluation_run_id=str(uuid4()), org_id=dataset["org_id"], dataset_version_id=dataset_version_id,
            provider=provider, model=model, model_version=model_version, prompt_version=prompt_version,
            started_at=self._now(), contract_count=dataset.get("contract_count", 0),
            ground_truth_count=dataset.get("ground_truth_finding_count", 0), created_by=self._uid(member),
            evaluator_version=evaluator_version, idempotency_key=idempotency_key,
            dataset_members=list(dataset_members or []),
        )
        self.runs.set(record.evaluation_run_id, record.model_dump(mode="json"))
        return record.model_dump(mode="json")

    def find_run(self, member: dict[str, Any], evaluation_run_id: str) -> dict[str, Any]:
        run = self.runs.get(evaluation_run_id)
        if not run:
            raise EvaluationNotFoundError(f"Evaluation run not found: {evaluation_run_id}")
        self._require_org_role(member, str(run.get("org_id") or ""), OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        return run

    def find_run_by_idempotency_key(self, member: dict[str, Any], *, dataset_version_id: str, idempotency_key: str) -> dict[str, Any] | None:
        """Return the existing run for this dataset + key, if one was already created."""
        if not idempotency_key:
            return None
        for run in self.runs.query(equal={"dataset_version_id": dataset_version_id}):
            if str(run.get("idempotency_key") or "") != idempotency_key:
                continue
            self._require_org_role(member, str(run.get("org_id") or ""), OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
            return run
        return None

    def update_run(self, member: dict[str, Any], evaluation_run_id: str, **fields: Any) -> dict[str, Any]:
        run = self.find_run(member, evaluation_run_id)
        allowed = {
            "status", "completed_at", "error_summary", "failed_contract_ids", "contract_errors",
            "contract_warnings", "ai_finding_count", "evaluator_version", "evaluated_at", "dataset_members",
            "idempotency_key",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        self.runs.set(evaluation_run_id, updates, merge=True)
        return {**run, **updates}

    def upsert_run_finding(self, member: dict[str, Any], evaluation_run_id: str, evaluation_finding_id: str, **fields: Any) -> dict[str, Any]:
        """Write one run finding under a caller-supplied deterministic id.

        Deterministic ids are what make re-processing the same provider output
        idempotent: the same (run, version, index, content hash) overwrites its own
        record instead of appending a duplicate.
        """
        run = self.find_run(member, evaluation_run_id)
        existing = self.run_findings.get(evaluation_finding_id)
        if existing and existing.get("evaluation_run_id") != evaluation_run_id:
            raise EvaluationError("Evaluation finding id belongs to a different run")
        record = EvaluationRunFinding(
            evaluation_finding_id=evaluation_finding_id, org_id=run["org_id"], evaluation_run_id=evaluation_run_id,
            dataset_version_id=run["dataset_version_id"], created_at=self._now(), **fields,
        )
        self.run_findings.set(record.evaluation_finding_id, record.model_dump(mode="json"))
        return record.model_dump(mode="json")

    def count_run_findings(self, member: dict[str, Any], evaluation_run_id: str) -> int:
        self.find_run(member, evaluation_run_id)
        return sum(1 for item in self.run_findings.query(equal={"evaluation_run_id": evaluation_run_id}))

    def list_run_findings(self, member: dict[str, Any], evaluation_run_id: str) -> list[dict[str, Any]]:
        self.find_run(member, evaluation_run_id)
        return sorted(
            self.run_findings.query(equal={"evaluation_run_id": evaluation_run_id}),
            key=lambda item: str(item.get("evaluation_finding_id") or ""),
        )

    def get_run_metrics(self, member: dict[str, Any], evaluation_run_id: str) -> dict[str, Any] | None:
        self.find_run(member, evaluation_run_id)
        return next(iter(self.metrics.query(equal={"evaluation_run_id": evaluation_run_id})), None)

    def add_run_finding(self, member: dict[str, Any], evaluation_run_id: str, **fields: Any) -> dict[str, Any]:
        run = self.runs.get(evaluation_run_id)
        if not run:
            raise EvaluationNotFoundError(f"Evaluation run not found: {evaluation_run_id}")
        self._require_org_role(member, run["org_id"], OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        record = EvaluationRunFinding(
            evaluation_finding_id=str(uuid4()), org_id=run["org_id"], evaluation_run_id=evaluation_run_id,
            dataset_version_id=run["dataset_version_id"], created_at=self._now(), **fields,
        )
        self.run_findings.set(record.evaluation_finding_id, record.model_dump(mode="json"))
        self.runs.set(evaluation_run_id, {"ai_finding_count": run.get("ai_finding_count", 0) + 1}, merge=True)
        return record.model_dump(mode="json")

    def add_match(self, member: dict[str, Any], evaluation_run_id: str, **fields: Any) -> dict[str, Any]:
        run = self.runs.get(evaluation_run_id)
        if not run:
            raise EvaluationNotFoundError(f"Evaluation run not found: {evaluation_run_id}")
        self._require_org_role(member, run["org_id"], OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        record = EvaluationMatch(
            evaluation_match_id=str(uuid4()), org_id=run["org_id"], evaluation_run_id=evaluation_run_id,
            created_at=self._now(), **fields,
        )
        self.matches.set(record.evaluation_match_id, record.model_dump(mode="json"))
        return record.model_dump(mode="json")

    def record_metrics(self, member: dict[str, Any], evaluation_run_id: str, **fields: Any) -> dict[str, Any]:
        run = self.runs.get(evaluation_run_id)
        if not run:
            raise EvaluationNotFoundError(f"Evaluation run not found: {evaluation_run_id}")
        self._require_org_role(member, run["org_id"], OrgRole.ADMIN.value, OrgRole.REVIEWER.value)
        record = EvaluationMetrics(
            evaluation_metrics_id=str(uuid4()), org_id=run["org_id"], evaluation_run_id=evaluation_run_id,
            calculated_at=self._now(), **fields,
        )
        self.metrics.set(record.evaluation_metrics_id, record.model_dump(mode="json"))
        return record.model_dump(mode="json")
