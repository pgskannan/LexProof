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


class InvalidStructuredProvider:
    async def complete(self, request):
        return type("Response", (), {"content": "not json"})()


class MissingFindingsProvider:
    async def complete(self, request):
        response = {"risk_score": 40, "risk_level": "MEDIUM", "compliance_score": 80, "key_clauses": [], "compliance_items": []}
        return type("Response", (), {"content": __import__("json").dumps(response)})()


class SecretLeakingProvider:
    async def complete(self, request):
        return type("Response", (), {"content": "{\"findings\": [\"secret-token\": \"sk-live-abc123\"]}"})()


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
    # Hardening item #3: real, measured Gemini call duration, timed directly
    # around the call rather than derived from broader lifecycle timestamps.
    # A freshly-created passport (this is a real Gemini call, not the cached-
    # snapshot short-circuit) must have this populated as a non-negative
    # number of milliseconds.
    passport_duration = FakeRepository.stores["legal_passports"][body["passport_id"]]["ai_analysis_duration_ms"]
    assert passport_duration is not None
    assert passport_duration >= 0


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


def test_invalid_provider_json_persists_safe_diagnostics(monkeypatch):
    client = make_client(monkeypatch, provider=InvalidStructuredProvider)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    assert response.json()["detail"] == "Vertex AI returned invalid structured analysis"
    version = FakeRepository.stores["contract_versions"]["version-2"]
    assert version["analysis_status"] == "failed"
    assert version["analysis_error"] == "ValueError"
    assert "not json" in version["error_detail"]
    assert "sk-live" not in version["error_detail"]


def test_missing_findings_in_structured_response_persists_diagnostics(monkeypatch):
    client = make_client(monkeypatch, provider=MissingFindingsProvider)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    version = FakeRepository.stores["contract_versions"]["version-2"]
    assert version["analysis_status"] == "failed"
    assert version["analysis_error"] == "ValueError"
    assert "findings" in version["error_detail"].lower()


def test_provider_exception_persists_safe_diagnostics(monkeypatch):
    client = make_client(monkeypatch, provider=FailingProvider)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    version = FakeRepository.stores["contract_versions"]["version-2"]
    assert version["analysis_status"] == "failed"
    assert version["analysis_error"] == "ValueError"
    assert "analysis failed" in version["error_detail"]


def test_analysis_failure_diagnostics_do_not_persist_sensitive_data(monkeypatch):
    client = make_client(monkeypatch, provider=SecretLeakingProvider)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    version = FakeRepository.stores["contract_versions"]["version-2"]
    assert version["analysis_status"] == "failed"
    assert "sk-live" not in str(version["error_detail"])
    assert "abc123" not in str(version["error_detail"])


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


# --- Finding Evidence Integrity (status doc §45) -----------------------------
#
# Gemini is instructed to return a verbatim `evidence_quote` per finding (see
# the prompt built in version_analysis.py), but nothing previously checked
# that claim against the actual source `document_text` before persisting the
# finding -- the mismatch was only ever discovered later, at publish time,
# when a human had already selected the finding, drafted a redline, and had
# it approved (see test_redline_proposals.py's publish-rejection tests for
# that existing, unchanged last line of defense). These four tests cover the
# new analysis-time `evidence_validation`/`evidence_match_count` fields
# computed in version_analysis.py's finding-persistence loop, using the
# exact same strict, unnormalized `str.count()` semantics as the publish
# guard: no whitespace normalization, no fuzzy matching, no second LLM call.

def _provider_with_finding(evidence_quote):
    """Build a FakeProvider-shaped class whose one finding carries exactly
    the given evidence_quote (empty string/omitted for the "no quote"
    case), reusing test-file conventions (async .complete(request) returning
    an object with .content = the JSON string)."""
    import json

    payload = {
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
            **({"evidence_quote": evidence_quote} if evidence_quote is not None else {}),
        }],
        "key_clauses": [{"text": "Revised clause text"}],
        "compliance_items": [],
    }

    class _Provider:
        async def complete(self, request):
            return type("Response", (), {"content": json.dumps(payload)})()

    return _Provider


def test_finding_evidence_validation_valid_when_quote_matches_source_exactly_once(monkeypatch):
    """The default fixture's evidence_quote ("Revised clause text") already
    matches version-2's document_text ("Revised clause text") exactly once
    -- the ordinary, correctly-extracted case."""
    client = make_client(monkeypatch)

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 200
    stored = next(iter(v for v in FakeRepository.stores["risk_findings"].values() if v.get("version_id") == "version-2"))
    assert stored["evidence_validation"] == "VALID"
    assert stored["evidence_match_count"] == 1


def test_finding_evidence_validation_invalid_when_quote_not_found_in_source(monkeypatch):
    """This is the exact real-world scenario this session's live browser
    Publish smoke test hit twice against the actual running app (status doc
    §45): an AI-claimed "exact" quote that does not occur in the source text
    at all."""
    client = make_client(monkeypatch, provider=_provider_with_finding("This sentence never appears in the document."))

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 200
    stored = next(iter(v for v in FakeRepository.stores["risk_findings"].values() if v.get("version_id") == "version-2"))
    assert stored["evidence_validation"] == "INVALID"
    assert stored["evidence_match_count"] == 0


def test_finding_evidence_validation_invalid_when_quote_matches_multiple_times(monkeypatch):
    """A quote that occurs more than once is exactly as unpublishable as one
    that occurs zero times -- the exact-match guard can't safely guess which
    occurrence is meant, so this must also validate as INVALID, not VALID."""
    client = make_client(monkeypatch, provider=_provider_with_finding("Revised clause text"))
    FakeRepository.stores["contract_versions"]["version-2"]["document_text"] = "Revised clause text. Revised clause text."

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 200
    stored = next(iter(v for v in FakeRepository.stores["risk_findings"].values() if v.get("version_id") == "version-2"))
    assert stored["evidence_validation"] == "INVALID"
    assert stored["evidence_match_count"] == 2


def test_finding_evidence_validation_invalid_when_quote_is_empty(monkeypatch):
    """An empty evidence_quote never reaches the new evidence-validation
    logic. The pre-existing, separately-tested passport validation layer
    (domains/passport/validation.py's AnalysisValidationError /
    REQUIRED_FINDING_FIELDS) requires evidence_quote to be a non-empty
    string for every finding, and rejects the whole AI analysis with a 502
    -- during passport creation, upstream of version_analysis.py's finding
    persistence -- before this finding is ever written with an
    evidence_validation/evidence_match_count value. This test documents
    that architectural boundary: the new source-match validation only ever
    runs on findings that already cleared this upstream required-fields
    guard. See status-and-plan.md §45 for the design discussion and
    tests/lexproof/passport/test_validation.py for that guard's own direct
    coverage."""
    client = make_client(monkeypatch, provider=_provider_with_finding(""))

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    assert response.json()["detail"] == "Vertex AI returned invalid structured analysis"


def test_finding_evidence_validation_invalid_when_quote_field_is_missing(monkeypatch):
    """Same architectural boundary as
    test_finding_evidence_validation_invalid_when_quote_is_empty, for a
    finding that omits the evidence_quote field entirely rather than
    supplying an empty string: the upstream passport validation layer's
    REQUIRED_FINDING_FIELDS check rejects it with a 502 before the new
    evidence-validation logic in version_analysis.py can ever run."""
    client = make_client(monkeypatch, provider=_provider_with_finding(None))

    response = client.post("/api/contracts/contract-1/versions/version-2/analyze")

    assert response.status_code == 502
    assert response.json()["detail"] == "Vertex AI returned invalid structured analysis"