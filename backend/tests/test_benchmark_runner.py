"""Isolated benchmark runner tests.

Every test uses in-memory repositories and a fake AI provider. No test calls
Vertex/Gemini, and production collections are guarded by a repository that raises
if the benchmark path ever attempts to write one of them.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.lexproof.services.analysis_prompt import ANALYSIS_PROMPT_VERSION, build_analysis_prompt
from app.lexproof.services.benchmark_runner import (
    BenchmarkRunService,
    map_ai_finding_to_run_finding,
    normalize_severity,
    run_finding_id,
    stable_run_key,
)
from app.lexproof.services.evaluation import (
    EvaluationError,
    EvaluationRunStatus,
    EvaluationService,
    EvaluationStatus,
    FindingSeverity,
)
from app.lexproof.services.evaluation_engine import EVALUATOR_VERSION
from app.lexproof.services.organizations import DEFAULT_PLAYBOOK_CLAUSES, OrganizationService

ORG_ID = "lexproof-demo"
OTHER_ORG_ID = "lexproof-other"
ADMIN = {"uid": "admin-1", "org_id": ORG_ID, "roles": ["admin"], "email": "admin@lexproof.test"}
REVIEWER = {"uid": "reviewer-1", "org_id": ORG_ID, "roles": ["reviewer"], "email": "reviewer@lexproof.test"}
OUTSIDER = {"uid": "admin-2", "org_id": OTHER_ORG_ID, "roles": ["admin"], "email": "other@lexproof.test"}

DATASET_ID = "9106833f-43df-4e0c-a78e-195ce30277af"
CONTRACT_SPECS = [
    ("contract-c2", "version-c2", "DOC-C2"),
    ("contract-c6", "version-c6", "DOC-C6"),
    ("contract-c8", "contract-c8", "DOC-C8"),
]
DECOY_VERSION_IDS = {contract_id: f"decoy-{contract_id}" for contract_id, _, _ in CONTRACT_SPECS}
PLAYBOOK = [{"clause_type": "limitation of liability", "standard_position": "cap at twelve months of fees"}]

GT_COLLECTION = "evaluation_ground_truth_findings"
GT_SPECS = [
    {
        "finding_category": "limitation of liability",
        "clause_reference": "Section 7",
        "expected_severity": FindingSeverity.HIGH,
        "expected_finding": "The liability cap is too low.",
        "expected_evidence": "Liability shall not exceed the fees paid in the twelve months preceding the claim.",
        "expected_recommendation": "Raise the cap.",
    },
    {
        "finding_category": "auto renewal",
        "clause_reference": "Section 2",
        "expected_severity": FindingSeverity.MEDIUM,
        "expected_finding": "The agreement renews automatically.",
        "expected_evidence": "This Agreement shall automatically renew for successive one-year terms.",
        "expected_recommendation": "Require written renewal.",
    },
]

# Collections the benchmark path must never write. contract_versions and contracts
# are readable but immutable for a benchmark run (no analysis_status/snapshot).
PRODUCTION_WRITE_COLLECTIONS = {
    "risk_findings",
    "legal_passports",
    "evidence_records",
    "evidence_anchors",
    "notifications",
    "audit_events",
    "contract_versions",
    "contracts",
}

WRITE_OPS = {"set", "delete"}


def asyncio_run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


class GuardedMemoryRepository:
    """In-memory repository that fails loudly on any production write."""

    def __init__(self, collection: str, store: dict[str, dict[str, dict]], access_log: list[tuple[str, str]]):
        self.collection = collection
        self._store = store
        self._log = access_log

    def _bucket(self) -> dict[str, dict]:
        return self._store.setdefault(self.collection, {})

    def _record(self, op: str) -> None:
        self._log.append((op, self.collection))
        if op in WRITE_OPS and self.collection in PRODUCTION_WRITE_COLLECTIONS:
            raise AssertionError(f"benchmark path attempted a production {op} on {self.collection}")

    def get(self, document_id: str, transaction: Any | None = None) -> dict[str, Any] | None:
        self._record("get")
        record = self._bucket().get(document_id)
        return dict(record) if record is not None else None

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False, transaction: Any | None = None) -> None:
        self._record("set")
        if merge:
            self._bucket().setdefault(document_id, {}).update(data)
        else:
            self._bucket()[document_id] = dict(data)

    def delete(self, document_id: str) -> None:
        self._record("delete")
        self._bucket().pop(document_id, None)

    def stream(self):
        self._record("stream")
        return iter({"id": key, **value} for key, value in self._bucket().items())

    def query(self, *, equal: dict[str, Any] | None = None, order_by: str | None = None, descending: bool = False, limit: int | None = None, **_: Any):
        self._record("query")
        records = [{"id": key, **value} for key, value in self._bucket().items()]
        for field_name, value in (equal or {}).items():
            records = [item for item in records if item.get(field_name) == value]
        if order_by:
            records.sort(key=lambda item: item.get(order_by) or "", reverse=descending)
        return records[:limit] if limit is not None else records


class FakeProvider:
    """Deterministic stand-in for VertexGeminiProvider. Never touches the network."""

    provider_name = "fake_vertex"

    def __init__(self, payloads: dict[str, dict], *, fail_for: tuple[str, ...] = (), model: str = "fake-gemini-1", access_log: list | None = None):
        self.payloads = payloads
        self.fail_for = set(fail_for)
        self.model = model
        self.prompts: list[str] = []
        self.markers: list[str | None] = []
        self.log_indices: list[int] = []
        self._access_log = access_log

    def supported_models(self) -> list[str]:
        return [self.model]

    async def complete(self, request: Any) -> SimpleNamespace:
        self.log_indices.append(len(self._access_log or []))
        self.prompts.append(request.prompt)
        marker = next((key for key in self.payloads if key in request.prompt), None)
        self.markers.append(marker)
        if marker in self.fail_for:
            raise RuntimeError("gemini exploded: api_key=sk-abcdef123456 token=supersecretvalue")
        return SimpleNamespace(content=json.dumps(self.payloads[marker]), model=self.model, provider=self.provider_name)


def ai_payload() -> dict[str, Any]:
    """Two AI findings: one that should match ground truth, one false positive."""
    return {
        "risk_score": 55,
        "compliance_score": 40,
        "risk_level": "HIGH",
        "detected_language": "en",
        "detected_language_name": "English",
        "findings": [
            {
                "title": "Liability cap",
                "severity": "HIGH",
                "description": "The liability cap is too low.",
                "evidence_quote": "Liability shall not exceed the fees paid in the twelve months preceding the claim.",
                "recommendation": "Raise the cap.",
                "source_section": "Section 7",
                "clause_type": "limitation of liability",
            },
            {
                "title": "Governing law",
                "severity": "low",
                "description": "Governing law is unfavorable.",
                "evidence_quote": "This Agreement is governed by the laws of Delaware.",
                "recommendation": "",
                "source_section": "Section 12",
                "clause_type": "governing law",
            },
        ],
        "key_clauses": [],
        "compliance_items": [],
    }


def payloads_for_all_contracts() -> dict[str, dict]:
    return {marker: ai_payload() for _, _, marker in CONTRACT_SPECS}


@dataclass
class Harness:
    service: EvaluationService
    store: dict[str, dict[str, dict]]
    access_log: list[tuple[str, str]]
    dataset_version_id: str = DATASET_ID
    documents: dict[str, str] = field(default_factory=dict)

    def repository_factory(self, collection: str) -> GuardedMemoryRepository:
        return GuardedMemoryRepository(collection, self.store, self.access_log)

    def runner(self, provider: FakeProvider, *, now: datetime | None = None, playbook: list[dict] | None = PLAYBOOK) -> BenchmarkRunService:
        clock = [now or datetime(2026, 1, 1, tzinfo=timezone.utc)]
        return BenchmarkRunService(
            evaluation=self.service,
            provider_factory=lambda: provider,
            playbook_provider=(lambda org_id: list(playbook)) if playbook is not None else None,
            now=lambda: clock[0],
        )

    def run_doc(self, run_id: str) -> dict[str, Any]:
        return self.store["evaluation_runs"][run_id]

    def collection(self, name: str) -> dict[str, dict]:
        return self.store.get(name, {})

    def ground_truth(self) -> list[dict[str, Any]]:
        return list(self.collection(GT_COLLECTION).values())

    def ai_findings(self, run_id: str) -> list[dict[str, Any]]:
        return [row for row in self.collection("evaluation_run_findings").values() if row.get("evaluation_run_id") == run_id]


def build_harness() -> Harness:
    store: dict[str, dict[str, dict]] = {}
    access_log: list[tuple[str, str]] = []

    for contract_id, version_id, marker in CONTRACT_SPECS:
        store.setdefault("contracts", {})[contract_id] = {
            "id": contract_id,
            "org_id": ORG_ID,
            # Deliberately NOT the benchmark version: the runner must use the frozen
            # dataset member version and never substitute current_version_id.
            "current_version_id": DECOY_VERSION_IDS[contract_id],
            "name": f"{marker}.docx",
        }
        store.setdefault("contract_versions", {})[version_id] = {
            "id": version_id,
            "contract_id": contract_id,
            "owner_id": ADMIN["uid"],
            "version_number": 1,
            "document_text": f"{marker}\n{marker} agreement text with Section 7 and Section 2.",
            "content_hash": f"hash-{marker.lower()}",
        }
        store.setdefault("contract_versions", {})[DECOY_VERSION_IDS[contract_id]] = {
            "id": DECOY_VERSION_IDS[contract_id],
            "contract_id": contract_id,
            "version_number": 2,
            "document_text": "LATER PRODUCTION VERSION THAT MUST NOT BE ANALYSED",
            "content_hash": "hash-decoy",
        }

    store.setdefault("organizations", {})[ORG_ID] = {"org_id": ORG_ID, "status": "active"}
    member_store = {
        ADMIN["uid"]: {"user_id": ADMIN["uid"], "org_id": ORG_ID, "status": "active", "roles": ["admin"]},
        REVIEWER["uid"]: {"user_id": REVIEWER["uid"], "org_id": ORG_ID, "status": "active", "roles": ["reviewer"]},
    }
    org_service = OrganizationService(
        orgs=GuardedMemoryRepository("organizations", store, access_log),
        users=GuardedMemoryRepository("users", store, access_log),
        invites=GuardedMemoryRepository("organization_invites", store, access_log),
        member_factory=lambda org_id: GuardedMemoryRepository(f"organizations/{org_id}/members", store, access_log),
    )
    store.setdefault("organization_members", {})[ADMIN["uid"]] = member_store[ADMIN["uid"]]

    service = EvaluationService(
        organizations=org_service,
        datasets=GuardedMemoryRepository("evaluation_datasets", store, access_log),
        members=GuardedMemoryRepository("evaluation_dataset_members", store, access_log),
        ground_truth=GuardedMemoryRepository(GT_COLLECTION, store, access_log),
        runs=GuardedMemoryRepository("evaluation_runs", store, access_log),
        run_findings=GuardedMemoryRepository("evaluation_run_findings", store, access_log),
        matches=GuardedMemoryRepository("evaluation_matches", store, access_log),
        metrics=GuardedMemoryRepository("evaluation_metrics", store, access_log),
        contracts=GuardedMemoryRepository("contracts", store, access_log),
        versions=GuardedMemoryRepository("contract_versions", store, access_log),
    )
    harness = Harness(service=service, store=store, access_log=access_log)
    for contract_id, version_id, _ in CONTRACT_SPECS:
        harness.documents[contract_id] = store["contract_versions"][version_id]["document_text"]

    # Seed the human benchmark with the real service: 3 members, 2 FINALIZED
    # findings each, then freeze the dataset.
    service.create_dataset(ADMIN, name="Internal Benchmark v1", description="", version_label="v1")
    # create_dataset generates its own id in this stub setup, so adopt whatever it stored.
    dataset_version_id = next(iter(store["evaluation_datasets"]))
    harness.dataset_version_id = dataset_version_id
    for contract_id, version_id, _ in CONTRACT_SPECS:
        service.add_dataset_member(ADMIN, dataset_version_id=dataset_version_id, contract_id=contract_id, version_id=version_id)
        for spec in GT_SPECS:
            finding = service.create_ground_truth(ADMIN, dataset_version_id=dataset_version_id, contract_id=contract_id, version_id=version_id, **spec)
            service.transition_ground_truth(ADMIN, finding["ground_truth_id"], EvaluationStatus.IN_REVIEW)
            service.transition_ground_truth(ADMIN, finding["ground_truth_id"], EvaluationStatus.APPROVED)
            service.transition_ground_truth(ADMIN, finding["ground_truth_id"], EvaluationStatus.FINALIZED)
    service.finalize_dataset(ADMIN, dataset_version_id)
    # The audit trail starts at the run, not at benchmark seeding (seeding reads
    # ground truth to drive the human transitions).
    access_log.clear()
    return harness


# --------------------------------------------------------------------------- A
def test_runner_requires_a_finalized_dataset():
    harness = build_harness()
    harness.store["evaluation_datasets"][harness.dataset_version_id]["status"] = "DRAFT"
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    with pytest.raises(EvaluationError):
        asyncio_run(harness.runner(provider).start_run(ADMIN, dataset_version_id=harness.dataset_version_id))

    assert harness.collection("evaluation_runs") == {}
    assert provider.prompts == []


def test_dataset_membership_is_denied_outside_the_organization():
    harness = build_harness()
    with pytest.raises(Exception):
        harness.runner(FakeProvider(payloads_for_all_contracts())).dataset_members(OUTSIDER, harness.dataset_version_id)


# --------------------------------------------------------------------------- B
def test_members_use_the_frozen_versions_in_added_at_order():
    harness = build_harness()
    _, members = harness.runner(FakeProvider(payloads_for_all_contracts())).dataset_members(ADMIN, harness.dataset_version_id)

    assert [member.contract_id for member in members] == [spec[0] for spec in CONTRACT_SPECS]
    assert [member.version_id for member in members] == [spec[1] for spec in CONTRACT_SPECS]
    # Never the contract's current production version.
    for member in members:
        assert member.version_id != DECOY_VERSION_IDS[member.contract_id]


def test_member_validation_rejects_a_version_that_does_not_belong_to_the_contract():
    harness = build_harness()
    member_row = next(iter(harness.collection("evaluation_dataset_members").values()))
    harness.store["contract_versions"][member_row["version_id"]]["contract_id"] = "some-other-contract"

    with pytest.raises(EvaluationError):
        harness.runner(FakeProvider(payloads_for_all_contracts())).dataset_members(ADMIN, harness.dataset_version_id)


def test_member_validation_rejects_a_version_without_document_text():
    harness = build_harness()
    first_version = CONTRACT_SPECS[0][1]
    harness.store["contract_versions"][first_version]["document_text"] = "   "

    with pytest.raises(EvaluationError):
        harness.runner(FakeProvider(payloads_for_all_contracts())).dataset_members(ADMIN, harness.dataset_version_id)


# --------------------------------------------------------------------- C, D, G
def run_benchmark(harness: Harness, provider: FakeProvider, **kwargs):
    return asyncio_run(
        harness.runner(provider).start_run(ADMIN, dataset_version_id=harness.dataset_version_id, **kwargs)
    )


def test_run_records_provenance_versions_and_content_hashes():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    result = run_benchmark(harness, provider)
    run = result["run"]

    assert run["status"] == EvaluationRunStatus.COMPLETED.value
    assert run["provider"] == "fake_vertex"
    assert run["model"] == "fake-gemini-1"
    assert run["model_version"] is None
    assert run["prompt_version"] == ANALYSIS_PROMPT_VERSION
    assert run["evaluator_version"] == EVALUATOR_VERSION
    assert run["created_by"] == ADMIN["uid"]
    assert run["started_at"] and run["completed_at"]
    assert run["dataset_version_id"] == harness.dataset_version_id
    assert run["contract_count"] == 3
    assert run["ground_truth_count"] == 6
    assert run["ai_finding_count"] == 6
    assert run["failed_contract_ids"] == []
    assert run["contract_errors"] == {}
    assert run["error_summary"] is None
    assert run["idempotency_key"] == stable_run_key(
        dataset_version_id=harness.dataset_version_id,
        provider="fake_vertex",
        model="fake-gemini-1",
        prompt_version=ANALYSIS_PROMPT_VERSION,
        evaluator_version=EVALUATOR_VERSION,
        version_ids=[spec[1] for spec in CONTRACT_SPECS],
    )
    assert run["dataset_members"] == [
        {
            "contract_id": contract_id,
            "version_id": version_id,
            "content_hash": harness.store["contract_versions"][version_id]["content_hash"],
            "added_at": run["dataset_members"][index]["added_at"],
            "document_text_length": len(harness.documents[contract_id]),
        }
        for index, (contract_id, version_id, _) in enumerate(CONTRACT_SPECS)
    ]
    assert all(entry["added_at"] for entry in run["dataset_members"])
    assert [entry["content_hash"] for entry in run["dataset_members"]] == ["hash-doc-c2", "hash-doc-c6", "hash-doc-c8"]


class PropertyModelProvider(FakeProvider):
    """Mirrors VertexGeminiProvider, which exposes supported_models as a property."""

    @property
    def supported_models(self) -> list[str]:
        return ["gemini-property-model"]


class SettingsOnlyProvider(FakeProvider):
    """A provider that advertises no model list at all."""

    supported_models = None

    def __init__(self, payloads: dict[str, dict], **kwargs: Any):
        super().__init__(payloads, **kwargs)
        self.settings = SimpleNamespace(gemini_model="gemini-from-settings")


def test_model_resolution_supports_the_vertex_providers_property():
    harness = build_harness()
    provider = PropertyModelProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    run = run_benchmark(harness, provider)["run"]

    assert run["model"] == "gemini-property-model"
    assert run["provider"] == "fake_vertex"
    assert run["status"] == EvaluationRunStatus.COMPLETED.value


def test_model_resolution_falls_back_to_the_provider_settings():
    harness = build_harness()
    provider = SettingsOnlyProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    run = run_benchmark(harness, provider)["run"]

    assert run["model"] == "gemini-from-settings"
    assert run["status"] == EvaluationRunStatus.COMPLETED.value


def test_explicit_model_overrides_provider_defaults():
    harness = build_harness()
    provider = PropertyModelProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    run = run_benchmark(harness, provider, model="gemini-pinned")["run"]

    assert run["model"] == "gemini-pinned"
    assert run["status"] == EvaluationRunStatus.COMPLETED.value


def test_run_writes_only_evaluation_run_data():
    harness = build_harness()
    versions_before = deepcopy(harness.store["contract_versions"])
    contracts_before = deepcopy(harness.store["contracts"])
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    run_benchmark(harness, provider)

    for collection in PRODUCTION_WRITE_COLLECTIONS:
        if collection in {"contract_versions", "contracts"}:
            continue
        assert harness.collection(collection) == {}, f"{collection} must stay untouched"
    # Still read-only: provenance of the frozen versions is unchanged.
    for version_id, record in versions_before.items():
        assert harness.store["contract_versions"][version_id] == record, "version documents must not be mutated"
    assert harness.store["contracts"] == contracts_before
    # No passports / evidence / anchors / notifications / audit events were created.
    assert "legal_passports" not in harness.store
    assert "evidence_anchors" not in harness.store


def test_ai_findings_are_stored_as_run_findings_with_deterministic_ids():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    result = run_benchmark(harness, provider)
    run_id = result["run"]["evaluation_run_id"]

    findings = harness.ai_findings(run_id)
    assert len(findings) == 6  # 2 findings per contract, 3 contracts

    for contract_id, version_id, _ in CONTRACT_SPECS:
        content_hash = harness.store["contract_versions"][version_id]["content_hash"]
        expected_ids = {
            run_finding_id(run_id, version_id, 0, content_hash),
            run_finding_id(run_id, version_id, 1, content_hash),
        }
        stored = {row["evaluation_finding_id"] for row in findings if row["version_id"] == version_id}
        assert stored == expected_ids
        assert all(row["evaluation_run_id"] == run_id for row in findings)
        assert all(row["dataset_version_id"] == harness.dataset_version_id for row in findings)
        assert all(row["contract_id"] == contract_id for row in findings if row["version_id"] == version_id)


def test_ground_truth_is_never_read_before_the_ai_has_produced_output():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    run_benchmark(harness, provider)

    gt_reads = [index for index, (op, collection) in enumerate(harness.access_log) if collection == GT_COLLECTION and op in {"get", "query", "stream"}]
    assert gt_reads, "the evaluator must read ground truth"
    assert all(index < gt_reads[0] for index in provider.log_indices), "no GT access may precede the AI output"
    # Exactly one AI call per benchmark version.
    assert len(provider.log_indices) == 3
    assert provider.markers == [spec[2] for spec in CONTRACT_SPECS]


def test_ground_truth_records_are_byte_identical_after_a_run():
    harness = build_harness()
    before = deepcopy(harness.ground_truth())
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    run_benchmark(harness, provider)

    assert harness.ground_truth() == before
    assert len(before) == 6
    assert {row["review_status"] for row in before} == {"FINALIZED"}


# --------------------------------------------------------------------------- H
def test_prompt_uses_the_shared_builder_and_contains_no_answer_key_material():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    run_benchmark(harness, provider)

    for index, prompt in enumerate(provider.prompts):
        document_text = harness.documents[CONTRACT_SPECS[index][0]]
        assert prompt == build_analysis_prompt(document_text, "- limitation of liability: cap at twelve months of fees")
        assert document_text in prompt
        for forbidden in ("ground_truth_id", "expected_finding", "expected_evidence", "expected_severity", "evaluation_ground_truth_findings", "reviewer_id", DATASET_ID):
            assert forbidden not in prompt


# --------------------------------------------------------------------------- C
def test_mapper_maps_ai_fields_and_normalizes_severity():
    mapped, warning = map_ai_finding_to_run_finding(
        {
            "title": "Liability cap",
            "description": "The liability cap is too low.",
            "severity": " high ",
            "evidence_quote": "Liability shall not exceed the fees paid.",
            "source_section": "Section 7",
            "clause_type": "limitation of liability",
            "recommendation": "Raise the cap.",
        },
        contract_id="contract-c2",
        version_id="version-c2",
        provider="fake_vertex",
        model="fake-gemini-1",
    )

    assert warning is None
    assert mapped == {
        "contract_id": "contract-c2",
        "version_id": "version-c2",
        "finding_category": "limitation of liability",
        "clause_reference": "Section 7",
        "severity": "HIGH",
        "finding": "The liability cap is too low.",
        "evidence": "Liability shall not exceed the fees paid.",
        "recommendation": "Raise the cap.",
        "provider": "fake_vertex",
        "model": "fake-gemini-1",
    }


def test_mapper_never_invents_a_severity_or_content():
    mapped, warning = map_ai_finding_to_run_finding(
        {"title": "X", "description": "Y", "severity": "SeVeRe", "evidence_quote": "Z", "source_section": "1", "clause_type": "other"},
        contract_id="c",
        version_id="v",
        provider="p",
        model="m",
    )

    assert mapped is None
    assert warning is not None and "SeVeRe" in warning
    assert normalize_severity(None) is None
    assert normalize_severity("critical") == "CRITICAL"
    assert normalize_severity("unknown") is None


def test_mapper_handles_missing_optional_fields_without_fabricating_content():
    mapped, warning = map_ai_finding_to_run_finding(
        {"severity": "MEDIUM", "title": "Only a title"},
        contract_id="c",
        version_id="v",
        provider="p",
        model="m",
    )

    assert warning is None
    assert mapped is not None
    assert mapped["finding"] == "Only a title"
    assert mapped["evidence"] == ""
    assert mapped["clause_reference"] == ""
    assert mapped["finding_category"] == "Other"
    assert mapped["recommendation"] is None


def test_unmappable_severity_is_recorded_as_a_warning_not_invented():
    harness = build_harness()
    payload = ai_payload()
    payload["findings"][1]["severity"] = "SeVeRe"
    provider = FakeProvider({marker: payload for _, _, marker in CONTRACT_SPECS}, access_log=harness.access_log)

    result = run_benchmark(harness, provider)

    run = result["run"]
    assert run["status"] == EvaluationRunStatus.COMPLETED.value
    assert run["contract_warnings"], "the omitted finding must be recorded"
    for warnings in run["contract_warnings"].values():
        assert any("SeVeRe" in warning for warning in warnings)
    # Only the mappable finding was stored; nothing was invented for the other.
    assert run["ai_finding_count"] == 3


# --------------------------------------------------------------------------- I
def test_completed_run_is_scored_by_the_deterministic_evaluator():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    result = run_benchmark(harness, provider)
    metrics = result["metrics"]
    run_id = result["run"]["evaluation_run_id"]

    assert metrics is not None
    assert metrics["evaluator_version"] == EVALUATOR_VERSION
    assert (metrics["true_positives"], metrics["false_positives"], metrics["false_negatives"]) == (3, 3, 3)
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["f1"] == pytest.approx(0.5)
    assert metrics["severity_accuracy"] == pytest.approx(1.0)
    assert metrics["critical_recall"] is None  # no CRITICAL ground truth: never claimed

    matches = list(harness.collection("evaluation_matches").values())
    assert len(matches) == 3 * (2 + 1)  # per contract: 2 GT rows, 1 false positive row
    assert all(row["evaluation_run_id"] == run_id for row in matches)
    assert all(row["evaluator_version"] == EVALUATOR_VERSION for row in matches)
    assert harness.run_doc(run_id)["evaluated_at"]

    # Scoring happens after the run and cannot touch the answer key.
    assert len(harness.ground_truth()) == 6
    assert {row["review_status"] for row in harness.ground_truth()} == {"FINALIZED"}


def test_evaluate_step_refuses_a_run_that_did_not_finish():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    result = run_benchmark(harness, provider, evaluate_after=False)
    run_id = result["run"]["evaluation_run_id"]
    harness.service.update_run(ADMIN, run_id, status=EvaluationRunStatus.FAILED.value)

    with pytest.raises(EvaluationError):
        asyncio_run(harness.runner(provider).evaluate_run(ADMIN, run_id))


# --------------------------------------------------------------------------- E
def test_partial_run_records_the_failed_contract_and_scores_the_rest():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), fail_for=("DOC-C6",), access_log=harness.access_log)
    before = deepcopy(harness.ground_truth())

    result = run_benchmark(harness, provider)
    run = result["run"]

    assert run["status"] == EvaluationRunStatus.PARTIAL.value
    assert run["failed_contract_ids"] == ["contract-c6"]
    error = run["contract_errors"]["contract-c6"]
    assert error.startswith("RuntimeError:")
    assert "api_key=[REDACTED]" in error and "sk-abcdef123456" not in error
    assert len(error) <= 300
    assert run["error_summary"] and len(run["error_summary"]) <= 1000
    assert run["ai_finding_count"] == 4  # C2 and C8 only
    assert result["metrics"] is not None  # processed contracts are still scored
    assert harness.ground_truth() == before


def test_failed_run_records_no_metrics_and_no_run_findings():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), fail_for=("DOC-C2", "DOC-C6", "DOC-C8"), access_log=harness.access_log)

    result = run_benchmark(harness, provider)
    run = result["run"]

    assert run["status"] == EvaluationRunStatus.FAILED.value
    assert result["metrics"] is None
    assert harness.collection("evaluation_metrics") == {}
    assert harness.collection("evaluation_matches") == {}
    assert harness.ai_findings(run["evaluation_run_id"]) == []
    assert set(run["failed_contract_ids"]) == {"contract-c2", "contract-c6", "contract-c8"}
    assert len(run["error_summary"]) <= 1000
    assert harness.ground_truth() and {row["review_status"] for row in harness.ground_truth()} == {"FINALIZED"}


def test_invalid_ai_output_fails_the_contract_with_a_bounded_error():
    harness = build_harness()
    payloads = payloads_for_all_contracts()
    payloads["DOC-C8"] = {"risk_score": 1}  # no findings list -> parser rejects it
    provider = FakeProvider(payloads, access_log=harness.access_log)

    result = run_benchmark(harness, provider)
    run = result["run"]

    assert run["status"] == EvaluationRunStatus.PARTIAL.value
    assert run["failed_contract_ids"] == ["contract-c8"]
    assert "omitted findings" in run["contract_errors"]["contract-c8"]


# --------------------------------------------------------------------------- D
def test_same_idempotency_key_reuses_the_run_and_never_duplicates_data():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    first = run_benchmark(harness, provider)
    run_id = first["run"]["evaluation_run_id"]
    findings_before = len(harness.ai_findings(run_id))
    matches_before = len(harness.collection("evaluation_matches"))
    metrics_before = len(harness.collection("evaluation_metrics"))

    # A second call with the same derived identity (no explicit key) must reuse it.
    unused_provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    second = run_benchmark(harness, unused_provider)

    assert second["reused"] is True
    assert second["run"]["evaluation_run_id"] == run_id
    assert unused_provider.prompts == [], "a reused run must not call the AI again"
    assert len(harness.collection("evaluation_runs")) == 1
    assert len(harness.ai_findings(run_id)) == findings_before
    assert len(harness.collection("evaluation_matches")) == matches_before
    assert len(harness.collection("evaluation_metrics")) == metrics_before


def test_an_explicit_key_is_respected_and_a_new_key_creates_a_comparison_run():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)

    first = run_benchmark(harness, provider, idempotency_key="approval-2026-09")
    again = run_benchmark(harness, FakeProvider(payloads_for_all_contracts()), idempotency_key="approval-2026-09")
    second = run_benchmark(harness, FakeProvider(payloads_for_all_contracts()), idempotency_key="approval-2026-10")

    assert first["run"]["idempotency_key"] == "approval-2026-09"
    assert again["reused"] is True and again["run"]["evaluation_run_id"] == first["run"]["evaluation_run_id"]
    assert second["reused"] is False
    assert second["run"]["evaluation_run_id"] != first["run"]["evaluation_run_id"]
    assert len(harness.collection("evaluation_runs")) == 2
    # Both runs are separately scorable and comparable.
    assert len(harness.collection("evaluation_metrics")) == 2


def test_reprocessing_the_same_provider_output_cannot_duplicate_run_findings():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    result = run_benchmark(harness, provider, evaluate_after=False)
    run_id = result["run"]["evaluation_run_id"]
    member = harness.runner(provider).dataset_members(ADMIN, harness.dataset_version_id)[1][0]
    before = len(harness.ai_findings(run_id))

    # Same run, same member, same provider output -> deterministic ids overwrite.
    for _ in range(2):
        harness.runner(provider)._persist_findings(
            ADMIN, run_id=run_id, item=member, analysis=ai_payload(), provider="fake_vertex", model="fake-gemini-1"
        )

    assert len(harness.ai_findings(run_id)) == before


# --------------------------------------------------------------------------- J
def test_run_report_exposes_provenance_and_metrics_without_the_answer_key():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    result = run_benchmark(harness, provider)
    report = harness.runner(provider).run_report(ADMIN, result["run"]["evaluation_run_id"])

    assert set(report) == {
        "evaluation_run_id", "status", "dataset_version_id", "provider", "model", "model_version",
        "prompt_version", "evaluator_version", "created_by", "started_at", "completed_at", "evaluated_at",
        "contract_count", "ground_truth_count", "ai_finding_count", "dataset_members", "failed_contract_ids",
        "contract_errors", "contract_warnings", "error_summary", "metrics",
    }
    assert report["metrics"]["precision"] == pytest.approx(0.5)
    assert report["metrics"]["true_positives"] == 3
    serialized = json.dumps(report)
    for forbidden in ("expected_finding", "expected_evidence", "expected_severity", "ground_truth_id", "limitation of liability is expected"):
        assert forbidden not in serialized
    assert GT_SPECS[0]["expected_evidence"] not in serialized
    assert GT_SPECS[0]["expected_finding"] not in serialized


def test_run_metadata_timestamps_come_from_the_injected_clock():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    clock = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)

    result = asyncio_run(
        harness.runner(provider, now=clock).start_run(ADMIN, dataset_version_id=harness.dataset_version_id)
    )

    assert result["run"]["completed_at"].startswith("2026-05-04T12:00")


def test_evaluator_version_change_is_reflected_in_run_metadata():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    runner = harness.runner(provider)

    class VersionedEvaluator:
        evaluator_version = "9.9.9-test"

    runner.evaluator = VersionedEvaluator()  # type: ignore[assignment]
    result = asyncio_run(runner.start_run(ADMIN, dataset_version_id=harness.dataset_version_id, evaluate_after=False))
    assert result["run"]["evaluator_version"] == "9.9.9-test"
    assert result["run"]["idempotency_key"] != stable_run_key(
        dataset_version_id=harness.dataset_version_id,
        provider="fake_vertex",
        model="fake-gemini-1",
        prompt_version=ANALYSIS_PROMPT_VERSION,
        evaluator_version=EVALUATOR_VERSION,
        version_ids=[spec[1] for spec in CONTRACT_SPECS],
    )


def test_default_playbook_provider_falls_back_to_the_default_clauses():
    harness = build_harness()
    provider = FakeProvider(payloads_for_all_contracts(), access_log=harness.access_log)
    runner = harness.runner(provider, playbook=None)

    result = asyncio_run(runner.start_run(ADMIN, dataset_version_id=harness.dataset_version_id, evaluate_after=False))

    assert result["run"]["status"] == EvaluationRunStatus.COMPLETED.value
    default_clause = DEFAULT_PLAYBOOK_CLAUSES[0]
    assert f"- {default_clause['clause_type']}: {default_clause['standard_position']}" in provider.prompts[0]


def test_hashes_and_ids_are_deterministic_across_processes():
    # sha256-based ids: same inputs -> same id, no clock or uuid involved.
    assert run_finding_id("run-1", "version-1", 0, "hash") == run_finding_id("run-1", "version-1", 0, "hash")
    assert run_finding_id("run-1", "version-1", 0, "hash") != run_finding_id("run-1", "version-1", 1, "hash")
    expected = hashlib.sha256("run-1|version-1|0|hash".encode("utf-8")).hexdigest()[:32]
    assert run_finding_id("run-1", "version-1", 0, "hash") == f"runfind_{expected}"
    assert stable_run_key(dataset_version_id="d", provider="p", model="m", prompt_version="v1", evaluator_version="e", version_ids=["a", "b"]) == stable_run_key(
        dataset_version_id="d", provider="p", model="m", prompt_version="v1", evaluator_version="e", version_ids=["a", "b"]
    )
