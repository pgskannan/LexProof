from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lexproof.api import findings as findings_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository


class FakeFindingsRepository:
    records = [
        {
            "id": "finding-1",
            "owner_id": "user-1",
            "contract_id": "contract-1",
            "version_id": "version-1",
            "title": "Liability cap",
            "severity": "critical",
            "description": "The cap is too low.",
            "risk_impact": 90,
            "compliance_impact": 20,
            "evidence": "Clause text",
            "evidence_quote": "Liability shall not exceed...",
            "source_section": "Section 12",
            "recommendation": "Review the cap.",
            "reasoning": "The cap of $10,000 is far below the demonstrated exposure in Section 9's indemnity scope.",
            "confidence": 0.85,
            "clause_type": "Limitation of Liability",
            "playbook_alignment": "DEVIATION",
            "playbook_notes": "The $10,000 cap is far below the standard 12-months-of-fees position.",
            "regulatory_citations": ["GDPR Article 28"],
            "evidence_validation": "VALID",
            "evidence_match_count": 1,
            "created_at": datetime.now(timezone.utc),
            "internal_value": "excluded",
        },
        {
            "id": "finding-2",
            "owner_id": "user-1",
            "contract_id": "contract-2",
            "version_id": "version-2",
            "title": "Notice period",
            "severity": "medium",
        },
        {
            "id": "finding-other-user",
            "owner_id": "user-2",
            "contract_id": "contract-1",
        },
    ]

    def __init__(self, collection: str):
        assert collection in {"risk_findings", "contracts"}
        self.collection = collection

    def stream(self):
        if self.collection == "contracts":
            return iter([
                {"id": "contract-1"},
                {"id": "contract-2"},
            ])
        return iter(self.records)

    def query(self, *, equal=None, **_):
        records = list(self.stream())
        for field, value in (equal or {}).items():
            records = [record for record in records if record.get(field) == value]
        return records

    def get(self, record_id: str):
        if self.collection == "contracts":
            return next((record for record in self.stream() if record.get("id") == record_id), None)
        return next((record for record in self.records if record.get("id") == record_id), None)

    def get_many(self, document_ids):
        found = {}
        for document_id in document_ids:
            record = self.get(str(document_id))
            if record:
                found[str(document_id)] = record
        return found


def make_client(monkeypatch):
    monkeypatch.setattr(findings_api, "FirestoreRepository", FakeFindingsRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    return TestClient(app)


def test_findings_require_authentication():
    response = TestClient(create_app()).get("/api/findings")
    assert response.status_code == 401


def test_findings_are_filtered_by_contract_and_version(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/findings?contract_id=contract-1&version_id=version-1")

    assert response.status_code == 200
    assert response.json() == [{
        "finding_id": "finding-1",
        "contract_id": "contract-1",
        "version_id": "version-1",
        "title": "Liability cap",
        "severity": "critical",
        "description": "The cap is too low.",
        "risk_impact": 90.0,
        "compliance_impact": 20.0,
        "evidence": "Clause text",
        "evidence_quote": "Liability shall not exceed...",
        "source_section": "Section 12",
        "recommendation": "Review the cap.",
        "reasoning": "The cap of $10,000 is far below the demonstrated exposure in Section 9's indemnity scope.",
        "confidence": 0.85,
        "clause_type": "Limitation of Liability",
        "playbook_alignment": "DEVIATION",
        "playbook_notes": "The $10,000 cap is far below the standard 12-months-of-fees position.",
        "regulatory_citations": ["GDPR Article 28"],
        "evidence_quote_masked": "Liability shall not exceed...",
        "contains_pii": False,
        "detected_language": None,
        "detected_language_name": None,
        "evidence_validation": "VALID",
        "evidence_match_count": 1,
        "created_at": response.json()[0]["created_at"],
    }]


def test_findings_return_empty_for_unknown_contract(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/findings?contract_id=missing")

    assert response.status_code == 200
    assert response.json() == []


def test_missing_optional_fields_remain_unavailable(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/findings?contract_id=contract-2&version_id=version-2")

    assert response.status_code == 200
    finding = response.json()[0]
    assert finding["risk_impact"] is None
    assert finding["compliance_impact"] is None
    assert finding["evidence_quote"] is None
    assert finding["source_section"] is None
    assert finding["reasoning"] is None
    assert finding["confidence"] is None
    assert finding["clause_type"] is None
    assert finding["playbook_alignment"] is None
    assert finding["playbook_notes"] is None
    assert finding["regulatory_citations"] == []
    assert finding["evidence_quote_masked"] is None
    assert finding["contains_pii"] is False
    assert finding["detected_language"] is None
    assert finding["detected_language_name"] is None
    assert finding["evidence_validation"] is None
    assert finding["evidence_match_count"] is None


def make_org_service() -> OrganizationService:
    service = OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )
    return service


def make_org_findings_client(monkeypatch, uid: str):
    FakeRepository.stores = {
        "organizations": {"org-1": {"org_id": "org-1", "status": "active"}},
        "users": {},
        "organization_invites": {},
        "organizations/org-1/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": "org-1"},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": "org-1"},
            "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": "org-1"},
        },
        "contracts": {"contract-1": {"id": "contract-1", "org_id": "org-1"}},
        "risk_findings": {
            "finding-1": {"id": "finding-1", "owner_id": "owner-1", "contract_id": "contract-1", "title": "Org finding"},
        },
    }
    service = make_org_service()
    monkeypatch.setattr(findings_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(findings_api, "get_organization_service", lambda: service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_same_org_admin_can_read_contract_findings(monkeypatch):
    response = make_org_findings_client(monkeypatch, "admin-1").get("/api/findings?contract_id=contract-1")
    assert response.status_code == 200
    assert response.json()[0]["finding_id"] == "finding-1"


def test_same_org_member_can_read_contract_findings(monkeypatch):
    response = make_org_findings_client(monkeypatch, "reviewer-1").get("/api/findings?contract_id=contract-1")
    assert response.status_code == 200
    assert response.json()[0]["finding_id"] == "finding-1"


def test_non_member_cannot_read_contract_findings(monkeypatch):
    response = make_org_findings_client(monkeypatch, "outside-1").get("/api/findings?contract_id=contract-1")
    assert response.status_code == 200
    assert response.json() == []


def test_legacy_finding_without_org_preserves_owner_only_visibility(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/findings?contract_id=contract-1")
    assert response.status_code == 200
    assert [item["finding_id"] for item in response.json()] == ["finding-1"]


class CountingFindingsRepository:
    """Same shape as FakeFindingsRepository, but records whether a
    contract-scoped list streamed the whole collection. list_findings() used
    to call repository.stream() and then filter in Python, so latency scaled
    with every risk_findings document (~180 demo findings -> 20s+, which
    left the findings page stuck on "—" inside the golden-path E2E timeout).
    A scoped request must query by contract_id instead, and only look up the
    matching record's contract for the visibility check."""

    records = [
        {"id": f"finding-{i}", "owner_id": "user-1", "contract_id": f"contract-{i}"}
        for i in range(50)
    ] + [
        {"id": "finding-target", "owner_id": "user-1", "contract_id": "contract-target", "title": "Target"},
    ]

    get_calls: list[str] = []
    query_equals: list[dict] = []
    stream_calls: int = 0

    def __init__(self, collection: str):
        assert collection in {"risk_findings", "contracts"}
        self.collection = collection

    def stream(self):
        if self.collection == "risk_findings":
            CountingFindingsRepository.stream_calls += 1
            return iter(self.records)
        return iter([{"id": f"contract-{i}"} for i in range(50)] + [{"id": "contract-target"}])

    def query(self, *, equal=None, **_):
        if self.collection == "risk_findings":
            CountingFindingsRepository.query_equals.append(dict(equal or {}))
        records = list(self.stream()) if self.collection != "risk_findings" else list(self.records)
        for field, value in (equal or {}).items():
            records = [record for record in records if record.get(field) == value]
        return records

    def get(self, record_id: str):
        if self.collection == "contracts":
            CountingFindingsRepository.get_calls.append(record_id)
            return next((record for record in self.stream() if record.get("id") == record_id), None)
        return next((record for record in self.records if record.get("id") == record_id), None)

    def get_many(self, document_ids):
        found = {}
        for document_id in document_ids:
            record = self.get(str(document_id))
            if record:
                found[str(document_id)] = record
        return found


def test_contract_scoped_query_does_not_scan_the_whole_collection(monkeypatch):
    CountingFindingsRepository.get_calls = []
    CountingFindingsRepository.query_equals = []
    CountingFindingsRepository.stream_calls = 0
    monkeypatch.setattr(findings_api, "FirestoreRepository", CountingFindingsRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    client = TestClient(app)

    response = client.get("/api/findings?contract_id=contract-target")

    assert response.status_code == 200
    assert [item["finding_id"] for item in response.json()] == ["finding-target"]
    assert CountingFindingsRepository.query_equals == [{"contract_id": "contract-target"}]
    assert CountingFindingsRepository.stream_calls == 0
    # Only the one matching record's contract should ever be looked up --
    # not all 51. Streaming the collection first would also trip stream_calls.
    assert CountingFindingsRepository.get_calls == ["contract-target"]


class SharedContractFindingsRepository:
    """Many findings on one contract: unscoped GET /api/findings must not
    call contracts.get() once per finding (the dashboard's unscoped fetch
    that saturates the backend when the smoke test runs before golden-path)."""

    records = [
        {"id": f"finding-{i}", "owner_id": "user-1", "contract_id": "contract-shared"}
        for i in range(40)
    ]

    get_calls: list[str] = []

    def __init__(self, collection: str):
        assert collection in {"risk_findings", "contracts"}
        self.collection = collection

    def stream(self):
        if self.collection == "contracts":
            return iter([{"id": "contract-shared"}])
        return iter(self.records)

    def query(self, *, equal=None, **_):
        records = list(self.stream())
        for field, value in (equal or {}).items():
            records = [record for record in records if record.get(field) == value]
        return records

    def get(self, record_id: str):
        if self.collection == "contracts":
            SharedContractFindingsRepository.get_calls.append(record_id)
            return {"id": record_id}
        return next((record for record in self.records if record.get("id") == record_id), None)

    def get_many(self, document_ids):
        found = {}
        for document_id in document_ids:
            record = self.get(str(document_id))
            if record:
                found[str(document_id)] = record
        return found


def test_unscoped_list_looks_up_each_contract_once(monkeypatch):
    SharedContractFindingsRepository.get_calls = []
    monkeypatch.setattr(findings_api, "FirestoreRepository", SharedContractFindingsRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    client = TestClient(app)

    response = client.get("/api/findings")

    assert response.status_code == 200
    assert len(response.json()) == 40
    assert SharedContractFindingsRepository.get_calls == ["contract-shared"]


def test_org_header_scopes_unscoped_list_to_that_org(monkeypatch):
    client = make_org_findings_client(monkeypatch, "admin-1")
    FakeRepository.stores["risk_findings"]["finding-1"]["org_id"] = "org-1"
    FakeRepository.stores["risk_findings"]["finding-other-org"] = {
        "id": "finding-other-org",
        "org_id": "org-2",
        "owner_id": "admin-1",
        "contract_id": "contract-2",
        "title": "Other org",
    }
    FakeRepository.stores["contracts"]["contract-2"] = {"id": "contract-2", "org_id": "org-2"}

    response = client.get("/api/findings", headers={"X-Org-Id": "org-1"})

    assert response.status_code == 200
    assert [item["finding_id"] for item in response.json()] == ["finding-1"]
