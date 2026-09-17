"""Route tests for benchmark finalization and the isolated evaluation runs.

Uses the in-memory benchmark harness from ``test_benchmark_runner`` and a fake AI
provider: no Firestore, no Vertex/Gemini, no real evaluation run.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.lexproof.api import evaluation as evaluation_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_org_member_from_header
from app.lexproof.services.evaluation import EvaluationService, EvaluationStatus
from tests.test_benchmark_runner import (
    ADMIN,
    CONTRACT_SPECS,
    DATASET_ID,
    GT_SPECS,
    ORG_ID,
    REVIEWER,
    FakeProvider,
    Harness,
    build_harness,
    payloads_for_all_contracts,
)

CONTRACT_OWNER = {"uid": "owner-1", "org_id": ORG_ID, "roles": ["contract_owner"], "email": "owner@lexproof.test"}
OUTSIDER = {"uid": "admin-2", "org_id": "lexproof-other", "roles": ["admin"], "email": "other@lexproof.test"}


class ApiHarness:
    """TestClient with the evaluation service/runner replaced by in-memory fakes."""

    def __init__(self, harness: Harness, provider: FakeProvider | None = None, member: dict | None = None):
        self.harness = harness
        self.provider = provider or FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
        self.member = member or ADMIN
        self.app = create_app()
        self.client = TestClient(self.app)
        self.app.dependency_overrides[get_current_org_member_from_header] = lambda: self.member
        self._original_service = evaluation_api._service
        self._original_runner = evaluation_api._runner
        evaluation_api._service = lambda: harness.service  # type: ignore[assignment]
        evaluation_api._runner = lambda: harness.runner(self.provider)  # type: ignore[assignment]

    def as_other_member(self, member: dict) -> "ApiHarness":
        self.member = member
        self.app.dependency_overrides[get_current_org_member_from_header] = lambda: member
        return self

    def close(self) -> None:
        evaluation_api._service = self._original_service  # type: ignore[assignment]
        evaluation_api._runner = self._original_runner  # type: ignore[assignment]
        self.app.dependency_overrides.clear()

    def __enter__(self) -> "ApiHarness":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


@pytest.fixture
def api():
    harness = build_harness()
    with ApiHarness(harness) as api:
        yield api


def dataset_path(harness: Harness) -> str:
    return f"/api/evaluation/benchmarks/{harness.dataset_version_id}"


def reopen_dataset(harness: Harness) -> None:
    """Undo the seeding-time finalization so the freeze transition is exercised."""
    row = harness.store["evaluation_datasets"][harness.dataset_version_id]
    row["status"] = "DRAFT"
    row.pop("finalized_at", None)


# ------------------------------------------------------------------ finalize
def test_finalize_requires_an_administrator(api: ApiHarness):
    reopen_dataset(api.harness)
    api.as_other_member(REVIEWER)
    response = api.client.post(f"{dataset_path(api.harness)}/finalize")

    assert response.status_code == 403
    assert api.harness.store["evaluation_datasets"][api.harness.dataset_version_id]["status"] == "DRAFT"


def test_finalize_freezes_the_dataset_and_is_idempotent(api: ApiHarness):
    harness = api.harness
    reopen_dataset(harness)
    findings_before = deepcopy(harness.ground_truth())

    first = api.client.post(f"{dataset_path(harness)}/finalize")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == EvaluationStatus.FINALIZED.value
    assert body["already_finalized"] is False
    assert body["member_count"] == 3
    assert body["finalized_at"]

    second = api.client.post(f"{dataset_path(harness)}/finalize")
    assert second.status_code == 200
    assert second.json()["already_finalized"] is True
    assert second.json()["finalized_at"] == body["finalized_at"]

    # Ground truth untouched, and no evaluation run was created by finalizing.
    assert harness.ground_truth() == findings_before
    assert harness.collection("evaluation_runs") == {}


def test_finalize_is_rejected_while_ground_truth_is_unfinished(api: ApiHarness):
    harness = api.harness
    reopen_dataset(harness)
    unfinished = harness.ground_truth()[0]
    harness.store["evaluation_ground_truth_findings"][unfinished["ground_truth_id"]]["review_status"] = "APPROVED"

    response = api.client.post(f"{dataset_path(harness)}/finalize")

    assert response.status_code == 400
    assert "finalized" in response.json()["detail"].lower()
    assert harness.store["evaluation_datasets"][harness.dataset_version_id]["status"] == "DRAFT"


def test_finalize_validates_member_contract_version_relationships(api: ApiHarness):
    harness = api.harness
    reopen_dataset(harness)
    first_version = CONTRACT_SPECS[0][1]
    harness.store["contract_versions"][first_version]["contract_id"] = "wrong-contract"

    response = api.client.post(f"{dataset_path(harness)}/finalize")

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]
    assert harness.store["evaluation_datasets"][harness.dataset_version_id]["status"] == "DRAFT"


def test_finalize_unknown_dataset_returns_404(api: ApiHarness):
    assert api.client.post("/api/evaluation/benchmarks/does-not-exist/finalize").status_code == 404


# ----------------------------------------------------------------------- runs
def test_create_run_requires_an_authorized_evaluation_role(api: ApiHarness):
    api.as_other_member(CONTRACT_OWNER)
    response = api.client.post("/api/evaluation/runs", json={"dataset_version_id": api.harness.dataset_version_id})

    assert response.status_code == 403
    assert api.harness.collection("evaluation_runs") == {}


def test_create_run_executes_the_benchmark_and_returns_a_report(api: ApiHarness):
    response = api.client.post("/api/evaluation/runs", json={"dataset_version_id": api.harness.dataset_version_id})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["reused"] is False
    assert body["provider"] == "fake_vertex"
    assert body["prompt_version"] == "analysis-1.0"
    assert body["evaluator_version"] == "1.0.0"
    assert body["contract_count"] == 3
    assert body["ground_truth_count"] == 6
    assert body["ai_finding_count"] == 6
    assert body["metrics"]["true_positives"] == 3
    assert body["failed_contract_ids"] == []
    assert len(body["dataset_members"]) == 3
    # The answer key is never echoed back through the results endpoint.
    raw = response.text
    for spec in GT_SPECS:
        assert spec["expected_finding"] not in raw
        assert spec["expected_evidence"] not in raw
    assert "ground_truth_id" not in raw


def test_create_run_denies_members_of_another_organization(api: ApiHarness):
    api.as_other_member(OUTSIDER)
    response = api.client.post("/api/evaluation/runs", json={"dataset_version_id": api.harness.dataset_version_id})

    assert response.status_code in {403, 404}
    assert api.harness.collection("evaluation_runs") == {}


def test_create_run_requires_a_finalized_dataset(api: ApiHarness):
    api.harness.store["evaluation_datasets"][api.harness.dataset_version_id]["status"] = "DRAFT"
    response = api.client.post("/api/evaluation/runs", json={"dataset_version_id": api.harness.dataset_version_id})

    assert response.status_code == 400
    assert "finalized dataset" in response.json()["detail"]
    assert api.harness.collection("evaluation_runs") == {}


def test_repeated_run_with_the_same_key_is_reused_through_the_api(api: ApiHarness):
    payload = {"dataset_version_id": api.harness.dataset_version_id, "idempotency_key": "approval-1"}
    first = api.client.post("/api/evaluation/runs", json=payload)
    second = api.client.post("/api/evaluation/runs", json=payload)

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["evaluation_run_id"] == second.json()["evaluation_run_id"]
    assert second.json()["reused"] is True
    assert len(api.harness.collection("evaluation_runs")) == 1
    assert len(api.harness.collection("evaluation_metrics")) == 1


def test_get_run_reports_status_and_metrics_without_ground_truth(api: ApiHarness):
    created = api.client.post("/api/evaluation/runs", json={"dataset_version_id": api.harness.dataset_version_id}).json()

    response = api.client.get(f"/api/evaluation/runs/{created['evaluation_run_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_run_id"] == created["evaluation_run_id"]
    assert body["metrics"]["f1"] == pytest.approx(0.5)
    assert body["metrics"]["uncertain_count"] == 0
    assert body["evaluated_at"]
    raw = response.text
    assert GT_SPECS[0]["expected_evidence"] not in raw
    assert "expected_severity" not in raw


def test_get_run_unknown_id_returns_404(api: ApiHarness):
    assert api.client.get("/api/evaluation/runs/does-not-exist").status_code == 404


def test_get_run_denies_a_contract_owner(api: ApiHarness):
    created = api.client.post("/api/evaluation/runs", json={"dataset_version_id": api.harness.dataset_version_id}).json()
    api.as_other_member(CONTRACT_OWNER)

    assert api.client.get(f"/api/evaluation/runs/{created['evaluation_run_id']}").status_code == 403


def test_evaluate_endpoint_rescores_a_run_without_touching_ground_truth(api: ApiHarness):
    harness = api.harness
    created = api.client.post(
        "/api/evaluation/runs", json={"dataset_version_id": harness.dataset_version_id, "evaluate": False}
    ).json()
    assert created["metrics"] is None
    findings_before = deepcopy(harness.ground_truth())

    response = api.client.post(f"/api/evaluation/runs/{created['evaluation_run_id']}/evaluate")

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["true_positives"] == 3
    assert body["evaluator_version"] == "1.0.0"
    assert body["metrics"]["evaluator_version"] == "1.0.0"
    assert harness.ground_truth() == findings_before


def test_evaluate_endpoint_rejects_a_run_with_no_usable_result(api: ApiHarness):
    harness = api.harness
    failing_provider = FakeProvider(payloads_for_all_contracts(), fail_for=("DOC-C2", "DOC-C6", "DOC-C8"))
    with ApiHarness(harness, provider=failing_provider) as failing_api:
        created = failing_api.client.post(
            "/api/evaluation/runs", json={"dataset_version_id": harness.dataset_version_id}
        ).json()
        assert created["status"] == "FAILED"
        assert created["metrics"] is None
        assert created["error_summary"]

        response = failing_api.client.post(f"/api/evaluation/runs/{created['evaluation_run_id']}/evaluate")

    assert response.status_code == 400
    assert harness.collection("evaluation_metrics") == {}


def test_benchmark_review_endpoints_are_unaffected(api: ApiHarness):
    """The AI-blind review workspace still works and still leaks nothing."""
    response = api.client.get(f"{dataset_path(api.harness)}/workspace")

    assert response.status_code == 200
    payload = response.json()
    assert sorted(payload) == ["contract_rows", "dataset", "ground_truth_findings", "review_progress"]
    assert payload["dataset"]["ai_blind"] is True
    assert len(payload["ground_truth_findings"]) == 6


def test_finalize_route_uses_the_existing_service_not_a_second_mechanism(api: ApiHarness):
    harness = api.harness
    reopen_dataset(harness)
    original = EvaluationService.finalize_dataset
    calls: list[tuple] = []

    def recording(self, member, dataset_version_id):
        calls.append((member.get("uid"), dataset_version_id))
        return original(self, member, dataset_version_id)

    EvaluationService.finalize_dataset = recording  # type: ignore[assignment]
    try:
        response = api.client.post(f"{dataset_path(harness)}/finalize")
    finally:
        EvaluationService.finalize_dataset = original  # type: ignore[assignment]

    assert response.status_code == 200
    assert calls == [(ADMIN["uid"], harness.dataset_version_id)]
