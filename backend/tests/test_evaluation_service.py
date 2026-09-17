"""Security and lifecycle tests for the isolated evaluation data model."""

from typing import Any

import pytest

from app.lexproof.services.evaluation import (
    EvaluationError,
    EvaluationMatchStatus,
    EvaluationPermissionError,
    EvaluationService,
    EvaluationStatus,
    EvaluationReviewType,
    GroundTruthSource,
    FindingSeverity,
)
from app.lexproof.services.organizations import OrganizationService, MEMBER_ACTIVE
from tests.fakes import FakeRepository


class LocalRepo:
    def __init__(self, initial: dict[str, dict] | None = None):
        self._data = dict(initial or {})

    def get(self, document_id: str, transaction: Any | None = None):
        record = self._data.get(document_id)
        return dict(record) if record is not None else None

    def set(self, document_id: str, data: dict, merge: bool = False, transaction: Any | None = None):
        if merge:
            current = self._data.setdefault(document_id, {})
            current.update(data)
        else:
            self._data[document_id] = dict(data)

    def stream(self):
        return iter({"id": key, **value} for key, value in self._data.items())


ORG_ID = "org-1"
OWNER = {"uid": "owner-1", "org_id": ORG_ID, "roles": ["contract_owner"]}
ADMIN = {"uid": "admin-1", "org_id": ORG_ID, "roles": ["admin"]}
REVIEWER = {"uid": "reviewer-1", "org_id": ORG_ID, "roles": ["reviewer"]}
AUDITOR = {"uid": "auditor-1", "org_id": ORG_ID, "roles": ["auditor"]}
OTHER_ORG_ADMIN = {"uid": "admin-2", "org_id": "org-2", "roles": ["admin"]}


def service() -> EvaluationService:
    org_store = {ORG_ID: {"org_id": ORG_ID, "status": "active"}}
    user_store = {
        "admin-1": {"user_id": "admin-1", "email": "admin@lexproof.test", "org_memberships": [ORG_ID]},
        "reviewer-1": {"user_id": "reviewer-1", "email": "reviewer@lexproof.test", "org_memberships": [ORG_ID]},
        "owner-1": {"user_id": "owner-1", "email": "owner@lexproof.test", "org_memberships": [ORG_ID]},
    }
    member_store = {
        "admin-1": {"user_id": "admin-1", "org_id": ORG_ID, "status": MEMBER_ACTIVE, "roles": ["admin"]},
        "reviewer-1": {"user_id": "reviewer-1", "org_id": ORG_ID, "status": MEMBER_ACTIVE, "roles": ["reviewer"]},
        "owner-1": {"user_id": "owner-1", "org_id": ORG_ID, "status": MEMBER_ACTIVE, "roles": ["contract_owner"]},
    }
    FakeRepository.stores = {
        "contracts": {"contract-1": {"id": "contract-1", "org_id": ORG_ID}},
        "contract_versions": {"version-1": {"id": "version-1", "contract_id": "contract-1"}},
    }
    org_service = OrganizationService(
        orgs=LocalRepo(org_store),
        users=LocalRepo(user_store),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: LocalRepo(member_store),
    )
    return EvaluationService(
        organizations=org_service,
        datasets=FakeRepository("evaluation_datasets"),
        members=FakeRepository("evaluation_dataset_members"),
        ground_truth=FakeRepository("evaluation_ground_truth_findings"),
        runs=FakeRepository("evaluation_runs"),
        run_findings=FakeRepository("evaluation_run_findings"),
        matches=FakeRepository("evaluation_matches"),
        metrics=FakeRepository("evaluation_metrics"),
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
    )


def finalized_ground_truth(evaluation: EvaluationService, dataset_id: str) -> str:
    finding = evaluation.create_ground_truth(
        REVIEWER,
        dataset_version_id=dataset_id,
        contract_id="contract-1",
        version_id="version-1",
        finding_category="limitation_of_liability",
        clause_reference="Section 7",
        expected_severity=FindingSeverity.HIGH,
        expected_finding="The liability cap is below the approved standard.",
        expected_evidence="Liability shall not exceed...",
        expected_recommendation="Review the cap.",
    )
    evaluation.transition_ground_truth(REVIEWER, finding["ground_truth_id"], EvaluationStatus.IN_REVIEW)
    evaluation.transition_ground_truth(REVIEWER, finding["ground_truth_id"], EvaluationStatus.APPROVED)
    evaluation.transition_ground_truth(REVIEWER, finding["ground_truth_id"], EvaluationStatus.FINALIZED)
    return finding["ground_truth_id"]


def test_admin_creates_dataset_and_members_reference_existing_version_only():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Legal Risk Benchmark", description="Demo evaluation", version_label="v1")

    member = evaluation.add_dataset_member(
        ADMIN,
        dataset_version_id=dataset["dataset_version_id"],
        contract_id="contract-1",
        version_id="version-1",
    )

    assert member["org_id"] == ORG_ID
    assert member["contract_id"] == "contract-1"
    assert member["version_id"] == "version-1"
    assert set(FakeRepository.stores) == {"contracts", "contract_versions", "evaluation_datasets", "evaluation_dataset_members"}


def test_ordinary_contract_owner_and_other_org_are_denied():
    evaluation = service()
    with pytest.raises(EvaluationPermissionError):
        evaluation.create_dataset(OWNER, name="No access", description="", version_label="v1")

    dataset = evaluation.create_dataset(ADMIN, name="Benchmark", description="", version_label="v1")
    with pytest.raises(EvaluationPermissionError):
        evaluation.get_dataset(OTHER_ORG_ADMIN, dataset["dataset_version_id"])


def test_ground_truth_lifecycle_and_finalized_immutability():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Benchmark", description="", version_label="v1")
    finding_id = finalized_ground_truth(evaluation, dataset["dataset_version_id"])
    finalized = evaluation.ground_truth.get(finding_id)
    assert finalized["review_status"] == "FINALIZED"
    assert finalized["finalized_at"]

    with pytest.raises(EvaluationError):
        evaluation.transition_ground_truth(REVIEWER, finding_id, EvaluationStatus.DRAFT)
    assert evaluation.ground_truth.get(finding_id)["review_status"] == "FINALIZED"


def test_finalized_ground_truth_correction_supersedes_without_mutating_original():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Benchmark", description="", version_label="v1")
    original_id = finalized_ground_truth(evaluation, dataset["dataset_version_id"])

    correction = evaluation.supersede_ground_truth(
        REVIEWER,
        original_id,
        expected_finding="Corrected expert finding.",
    )

    assert correction["supersedes_id"] == original_id
    assert correction["review_status"] == "DRAFT"
    assert evaluation.ground_truth.get(original_id)["review_status"] == "FINALIZED"


def test_dataset_finalization_requires_finalized_ground_truth_and_run_ownership():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Benchmark", description="", version_label="v1")
    evaluation.add_dataset_member(ADMIN, dataset_version_id=dataset["dataset_version_id"], contract_id="contract-1", version_id="version-1")
    draft = evaluation.create_ground_truth(
        REVIEWER,
        dataset_version_id=dataset["dataset_version_id"],
        contract_id="contract-1",
        version_id="version-1",
        finding_category="limitation_of_liability",
        clause_reference="Section 7",
        expected_severity=FindingSeverity.HIGH,
        expected_finding="Draft expert finding.",
        expected_evidence="Liability shall not exceed...",
    )
    with pytest.raises(EvaluationError):
        evaluation.finalize_dataset(ADMIN, dataset["dataset_version_id"])
    evaluation.transition_ground_truth(REVIEWER, draft["ground_truth_id"], EvaluationStatus.IN_REVIEW)
    evaluation.transition_ground_truth(REVIEWER, draft["ground_truth_id"], EvaluationStatus.APPROVED)
    evaluation.transition_ground_truth(REVIEWER, draft["ground_truth_id"], EvaluationStatus.FINALIZED)

    finalized = evaluation.finalize_dataset(ADMIN, dataset["dataset_version_id"])
    assert finalized["status"] == "FINALIZED"
    run = evaluation.create_run(ADMIN, dataset_version_id=dataset["dataset_version_id"], provider="vertex_ai", model="gemini-test")
    with pytest.raises(EvaluationPermissionError):
        evaluation.get_dataset(OTHER_ORG_ADMIN, dataset["dataset_version_id"])
    assert evaluation.get_dataset(AUDITOR, dataset["dataset_version_id"])["status"] == "FINALIZED"
    assert run["org_id"] == ORG_ID


def test_evaluation_outputs_are_isolated_and_match_states_are_supported():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Benchmark", description="", version_label="v1")
    finalized_ground_truth(evaluation, dataset["dataset_version_id"])
    evaluation.finalize_dataset(ADMIN, dataset["dataset_version_id"])
    run = evaluation.create_run(ADMIN, dataset_version_id=dataset["dataset_version_id"], provider="vertex_ai", model="gemini-test")
    finding = evaluation.add_run_finding(
        REVIEWER,
        run["evaluation_run_id"],
        contract_id="contract-1",
        version_id="version-1",
        finding_category="limitation_of_liability",
        clause_reference="Section 7",
        severity=FindingSeverity.HIGH,
        finding="The liability cap is below the approved standard.",
        evidence="Liability shall not exceed...",
        provider="vertex_ai",
        model="gemini-test",
    )
    match = evaluation.add_match(
        REVIEWER,
        run["evaluation_run_id"],
        ground_truth_id=next(iter(FakeRepository.stores["evaluation_ground_truth_findings"])),
        evaluation_finding_id=finding["evaluation_finding_id"],
        contract_id="contract-1",
        version_id="version-1",
        status=EvaluationMatchStatus.MATCHED,
        match_reason="same category and clause reference",
    )
    metrics = evaluation.record_metrics(REVIEWER, run["evaluation_run_id"], precision=1.0, recall=1.0, f1=1.0)

    assert match["status"] == "MATCHED"
    assert metrics["precision"] == 1.0
    assert "risk_findings" not in FakeRepository.stores
    assert "legal_passports" not in FakeRepository.stores
    assert "evidence_records" not in FakeRepository.stores
    assert "redline_proposals" not in FakeRepository.stores


def test_internal_dataset_metadata_and_human_entry_do_not_copy_ai_values():
    evaluation = service()
    dataset = evaluation.create_dataset(
        ADMIN,
        name="LexProof Internal Benchmark v1",
        description="Internal review shell",
        version_label="v1",
        review_type=EvaluationReviewType.INTERNAL_REVIEW,
        reviewer_type="INTERNAL_REVIEWER",
        reviewer_id=REVIEWER["uid"],
        ai_blind=True,
        ground_truth_source=GroundTruthSource.INTERNAL_HUMAN_REVIEW,
    )
    assert dataset["review_type"] == "INTERNAL_REVIEW"
    assert dataset["ai_blind"] is True
    assert dataset["ground_truth_source"] == "INTERNAL_HUMAN_REVIEW"

    finding = evaluation.create_ground_truth(
        REVIEWER,
        dataset_version_id=dataset["dataset_version_id"],
        contract_id="contract-1",
        version_id="version-1",
        finding_category="limitation_of_liability",
        clause_reference="Section 7",
        expected_severity=FindingSeverity.HIGH,
        expected_finding="Human independently identified finding.",
        expected_evidence="Human-selected contract evidence.",
        expected_recommendation="Human-selected recommendation.",
    )
    assert "AI-GENERATED-SHOULD-NOT-COPY" not in str(finding)
    assert "AI-ONLY-TEST" not in str(finding)


def test_independent_dataset_requires_explicit_review_metadata():
    evaluation = service()
    with pytest.raises(EvaluationError):
        evaluation.create_dataset(
            ADMIN,
            name="LexProof Independent Benchmark v1",
            description="Future independent review",
            version_label="v1",
            review_type=EvaluationReviewType.INDEPENDENT_REVIEW,
            reviewer_type="INTERNAL_REVIEWER",
            reviewer_id=None,
            ground_truth_source=GroundTruthSource.INTERNAL_HUMAN_REVIEW,
        )


def test_internal_and_independent_datasets_are_separate():
    evaluation = service()
    internal = evaluation.create_dataset(ADMIN, name="Internal", description="", version_label="v1")
    assert internal["review_type"] == "INTERNAL_REVIEW"
    assert [row for row in evaluation.datasets.stream() if row["review_type"] == "INDEPENDENT_REVIEW"] == []


def test_dataset_review_list_uses_ground_truth_only_and_respects_assignment_access():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Internal Benchmark v1", description="", version_label="v1")
    evaluation.add_dataset_member(ADMIN, dataset_version_id=dataset["dataset_version_id"], contract_id="contract-1", version_id="version-1")

    finding = evaluation.create_ground_truth(
        REVIEWER,
        dataset_version_id=dataset["dataset_version_id"],
        contract_id="contract-1",
        version_id="version-1",
        finding_category="limitation_of_liability",
        clause_reference="Section 7",
        expected_severity=FindingSeverity.HIGH,
        expected_finding="Human-reviewed issue",
        expected_evidence="The liability cap is low.",
        expected_recommendation="Increase the cap.",
    )
    evaluation.assign_ground_truth(REVIEWER, finding["ground_truth_id"], "admin-1")

    rows = evaluation.list_ground_truth_findings(REVIEWER, dataset["dataset_version_id"], contract_id="contract-1")
    assert len(rows) == 1
    assert rows[0]["finding_category"] == "limitation_of_liability"
    assert rows[0]["reviewer_id"] == "admin-1"

    with pytest.raises(EvaluationPermissionError):
        evaluation.assign_ground_truth(OWNER, finding["ground_truth_id"], "reviewer-1")


def test_ai_blind_review_payload_excludes_production_and_eval_collections():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Internal Benchmark v1", description="", version_label="v1")
    finding = evaluation.create_ground_truth(
        REVIEWER,
        dataset_version_id=dataset["dataset_version_id"],
        contract_id="contract-1",
        version_id="version-1",
        finding_category="limitation_of_liability",
        clause_reference="Section 7",
        expected_severity=FindingSeverity.HIGH,
        expected_finding="Human-reviewed issue",
        expected_evidence="The liability cap is low.",
        expected_recommendation="Increase the cap.",
    )

    payload = evaluation.get_review_workspace_payload(REVIEWER, dataset["dataset_version_id"], contract_id="contract-1")
    assert payload["ground_truth_findings"][0]["ground_truth_id"] == finding["ground_truth_id"]
    assert "risk_findings" not in payload
    assert "evaluation_run_findings" not in payload
    assert "evaluation_matches" not in payload
    assert "evaluation_metrics" not in payload


def test_review_workspace_contract_rows_expose_the_dataset_insertion_order():
    evaluation = service()
    dataset = evaluation.create_dataset(ADMIN, name="Internal Benchmark v1", description="", version_label="v1")
    added = evaluation.add_dataset_member(
        ADMIN,
        dataset_version_id=dataset["dataset_version_id"],
        contract_id="contract-1",
        version_id="version-1",
    )

    payload = evaluation.get_review_workspace_payload(REVIEWER, dataset["dataset_version_id"])

    row = payload["contract_rows"][0]
    assert row["contract_id"] == "contract-1"
    # The reviewer's "Continue to Next Contract" orders the workspace by this
    # value, so it must survive the payload unchanged.
    assert row["added_at"] == added["added_at"]
    assert row["added_at"] is not None