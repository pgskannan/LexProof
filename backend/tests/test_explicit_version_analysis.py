from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user


class FakeRepository:
    stores: dict[str, dict[str, dict]] = {}

    def __init__(self, collection: str):
        self.collection = collection

    def get(self, document_id: str):
        return self.stores.setdefault(self.collection, {}).get(document_id)

    def set(self, document_id: str, data: dict, merge: bool = False):
        collection = self.stores.setdefault(self.collection, {})
        if merge:
            collection.setdefault(document_id, {}).update(data)
        else:
            collection[document_id] = dict(data)

    def stream(self):
        return iter({"id": key, **value} for key, value in self.stores.setdefault(self.collection, {}).items())


ANALYSIS = {
    "risk_score": 40,
    "risk_level": "MEDIUM",
    "compliance_score": 80,
    "findings": [{
        "title": "Updated liability",
        "severity": "medium",
        "description": "The revised clause needs review.",
        "evidence": "Revised clause text",
        "recommendation": "Confirm the revised cap.",
        "risk_impact": 40,
        "compliance_impact": 80,
        "source_section": "Section 4",
        "evidence_quote": "Revised clause text",
    }],
    "key_clauses": [{"text": "Revised clause text"}],
    "compliance_items": [],
}


class FakeProvider:
    calls = 0

    async def complete(self, request):
        FakeProvider.calls += 1
        assert "Revised clause text" in request.prompt
        return type("Response", (), {"content": __import__("json").dumps(ANALYSIS)})()


class FailingProvider:
    async def complete(self, request):
        raise ValueError("analysis failed")


class FakeAnchorService:
    calls = 0

    def __init__(self, repository, evidence_repository):
        self.repository = repository
        self.evidence_repository = evidence_repository

    async def anchor_evidence(self, evidence_id):
        FakeAnchorService.calls += 1
        evidence = self.evidence_repository.get(evidence_id)
        evidence_hash = __import__("app.lexproof.domains.passport.utils.hashing", fromlist=["hash_evidence_item"]).hash_evidence_item(evidence)
        existing = self.repository.get(evidence_id)
        if existing:
            assert existing["evidence_hash"] == evidence_hash
            return existing
        proof = {"evidence_id": evidence_id, "evidence_hash": evidence_hash, "transaction_hash": "fake-tx", "block_number": 1}
        self.repository.set(evidence_id, proof)
        return proof


class FailingAnchorService(FakeAnchorService):
    async def anchor_evidence(self, evidence_id):
        raise RuntimeError("anchor failed")


class FailOnceRepository(FakeRepository):
    failure: tuple[str, int] | None = None
    counts: dict[str, int] = {}

    def set(self, document_id: str, data: dict, merge: bool = False):
        self.counts[self.collection] = self.counts.get(self.collection, 0) + 1
        if self.failure == (self.collection, self.counts[self.collection]):
            self.failure = None
            raise RuntimeError(f"failure after {self.collection}")
        return super().set(document_id, data, merge=merge)


class FailOnceAnchorService(FakeAnchorService):
    failed = False
    attempts = 0

    async def anchor_evidence(self, evidence_id):
        type(self).attempts += 1
        if not self.failed and type(self).attempts == 2:
            self.failed = True
            evidence = self.evidence_repository.get(evidence_id)
            evidence_hash = __import__("app.lexproof.domains.passport.utils.hashing", fromlist=["hash_evidence_item"]).hash_evidence_item(evidence)
            self.repository.set(evidence_id, {"evidence_hash": evidence_hash})
            raise RuntimeError("failure after one Ethereum anchor")
        return await super().anchor_evidence(evidence_id)


def seed_data():
    FakeProvider.calls = 0
    FakeAnchorService.calls = 0
    FailOnceRepository.failure = None
    FailOnceRepository.counts = {}
    FailOnceAnchorService.failed = False
    FailOnceAnchorService.attempts = 0
    FakeRepository.stores = {
        "contracts": {"contract-1": {"id": "contract-1", "owner_id": "owner-1", "current_version_id": "version-2"}},
        "contract_versions": {
            "version-1": {"id": "version-1", "contract_id": "contract-1", "owner_id": "owner-1", "version_number": 1, "document_text": "Original clause"},
            "version-2": {"id": "version-2", "contract_id": "contract-1", "owner_id": "owner-1", "version_number": 2, "parent_version_id": "version-1", "document_text": "Revised clause text"},
        },
        "legal_passports": {"passport-v1": {"id": "passport-v1", "passport_id": "passport-v1", "contract_id": "contract-1", "contract_version": 1, "owner_id": "owner-1"}},
        "risk_findings": {"finding-v1": {"id": "finding-v1", "contract_id": "contract-1", "version_id": "version-1", "owner_id": "owner-1"}},
        "evidence_records": {"evidence-v1": {"id": "evidence-v1", "evidence_id": "evidence-v1", "passport_id": "passport-v1", "contract_id": "contract-1", "contract_version": 1, "owner_id": "owner-1", "evidence_type": "clause"}},
    }


def make_client(monkeypatch, provider=FakeProvider, uid="owner-1"):
    seed_data()
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "_repositories", lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()))
    monkeypatch.setattr(contracts_api, "VertexGeminiProvider", provider)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "get_ethereum_anchor_service", lambda **kwargs: FakeAnchorService(kwargs["repository"], kwargs["evidence_repository"]))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def make_retry_client(monkeypatch, failure, anchor_factory=None):
    seed_data()
    FailOnceRepository.failure = failure
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FailOnceRepository)
    monkeypatch.setattr(contracts_api, "_repositories", lambda: (FailOnceRepository("contracts"), FailOnceRepository("contract_versions"), object()))
    monkeypatch.setattr(contracts_api, "VertexGeminiProvider", FakeProvider)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", FailOnceRepository)
    monkeypatch.setattr(contracts_api, "get_ethereum_anchor_service", anchor_factory or (lambda **kwargs: FakeAnchorService(kwargs["repository"], kwargs["evidence_repository"])))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    return TestClient(app)


def test_explicit_v2_analysis_creates_distinct_versioned_artifacts(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["version_id"] == "version-2"
    assert body["version_number"] == 2
    assert body["analysis_status"] == "complete"
    assert body["finding_count"] == 1
    assert body["evidence_count"] == 1
    assert FakeRepository.stores["contract_versions"]["version-2"]["analysis_status"] == "complete"
    assert FakeRepository.stores["contract_versions"]["version-2"]["passport_id"] == body["passport_id"]
    assert len(FakeRepository.stores["legal_passports"]) == 2
    v2_findings = [item for item in FakeRepository.stores["risk_findings"].values() if item.get("version_id") == "version-2"]
    v2_evidence = [item for item in FakeRepository.stores["evidence_records"].values() if item.get("contract_version") == 2 and item.get("evidence_type") != "metadata"]
    v2_metadata = [item for item in FakeRepository.stores["evidence_records"].values() if item.get("contract_version") == 2 and item.get("evidence_type") == "metadata"]
    assert len(v2_findings) == 1
    assert len(v2_evidence) == 1
    assert len(v2_metadata) == 1
    assert v2_evidence[0]["passport_id"] == body["passport_id"]
    assert FakeRepository.stores["risk_findings"]["finding-v1"]["version_id"] == "version-1"
    assert FakeRepository.stores["evidence_records"]["evidence-v1"]["passport_id"] == "passport-v1"
    assert FakeRepository.stores["legal_passports"][body["passport_id"]]["metadata"]["clauses"]


def test_repeated_v2_analysis_is_idempotent(monkeypatch):
    client = make_client(monkeypatch)
    first = client.post("/api/contracts/contract-1/versions/version-2/analyze").json()
    second = client.post("/api/contracts/contract-1/versions/version-2/analyze").json()

    assert second == first
    assert FakeProvider.calls == 1
    assert FakeAnchorService.calls == 2
    assert len(FakeRepository.stores["legal_passports"]) == 2


def test_explicit_analysis_rejects_unauthorized_cross_contract_missing_and_empty(monkeypatch):
    unauthorized = make_client(monkeypatch, uid="other-user")
    assert unauthorized.post("/api/contracts/contract-1/versions/version-2/analyze").status_code == 403
    client = make_client(monkeypatch)
    assert client.post("/api/contracts/contract-1/versions/missing/analyze").status_code == 404
    FakeRepository.stores["contract_versions"]["version-2"]["document_text"] = ""
    assert client.post("/api/contracts/contract-1/versions/version-2/analyze").status_code == 422


def test_explicit_analysis_rejects_non_current_version_without_creating_artifacts(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post("/api/contracts/contract-1/versions/version-1/analyze")

    assert response.status_code == 409
    assert len(FakeRepository.stores["legal_passports"]) == 1
    assert FakeProvider.calls == 0


def test_failed_explicit_analysis_marks_version_failed_not_complete(monkeypatch):
    client = make_client(monkeypatch, provider=FailingProvider)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    assert FakeRepository.stores["contract_versions"]["version-2"]["analysis_status"] == "failed"
    assert len(FakeRepository.stores["legal_passports"]) == 1
    assert len(FakeRepository.stores["evidence_records"]) == 1


def test_failed_anchor_marks_version_failed_not_complete(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(
        contracts_api,
        "get_ethereum_anchor_service",
        lambda **kwargs: FailingAnchorService(kwargs["repository"], kwargs["evidence_repository"]),
    )

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    assert response.json()["detail"] == "Ethereum anchoring failed"
    assert FakeRepository.stores["contract_versions"]["version-2"]["analysis_status"] == "failed"


def test_retry_after_partial_artifacts_reuses_passport_findings_and_evidence(monkeypatch):
    client = make_retry_client(monkeypatch, ("risk_findings", 1))
    first = client.post("/api/contracts/contract-1/versions/version-2/analyze")
    assert first.status_code == 502
    assert FakeRepository.stores["contract_versions"]["version-2"]["analysis_status"] == "failed"
    passport_count = len(FakeRepository.stores["legal_passports"])
    finding_count = len(FakeRepository.stores["risk_findings"])
    evidence_count = len(FakeRepository.stores["evidence_records"])

    retry = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert retry.status_code == 200
    assert len(FakeRepository.stores["legal_passports"]) == passport_count
    assert len(FakeRepository.stores["risk_findings"]) == finding_count + 1
    assert len(FakeRepository.stores["evidence_records"]) == evidence_count + 2
    assert FakeProvider.calls == 1
    assert FakeRepository.stores["contract_versions"]["version-1"]["version_number"] == 1


@pytest.mark.parametrize("failure", [("legal_passports", 2), ("risk_findings", 1), ("evidence_records", 1)])
def test_retry_after_each_persistence_stage_is_recoverable(monkeypatch, failure):
    client = make_retry_client(monkeypatch, failure)
    assert client.post("/api/contracts/contract-1/versions/version-2/analyze").status_code == 502
    assert client.post("/api/contracts/contract-1/versions/version-2/analyze").status_code == 200
    assert FakeRepository.stores["contract_versions"]["version-2"]["analysis_status"] == "complete"


def test_retry_after_one_anchor_does_not_duplicate_anchor_or_artifacts(monkeypatch):
    client = make_retry_client(
        monkeypatch,
        None,
        anchor_factory=lambda **kwargs: FailOnceAnchorService(kwargs["repository"], kwargs["evidence_repository"]),
    )
    first = client.post("/api/contracts/contract-1/versions/version-2/analyze")
    assert first.status_code == 502
    passport_count = len(FakeRepository.stores["legal_passports"])
    finding_count = len(FakeRepository.stores["risk_findings"])
    evidence_count = len(FakeRepository.stores["evidence_records"])
    retry = client.post("/api/contracts/contract-1/versions/version-2/analyze")
    assert retry.status_code == 200
    assert len(FakeRepository.stores["legal_passports"]) == passport_count
    assert len(FakeRepository.stores["risk_findings"]) == finding_count
    assert len(FakeRepository.stores["evidence_records"]) == evidence_count


def test_explicit_analysis_does_not_expose_document_content(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 200
    assert "document_text" not in response.json()