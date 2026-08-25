from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lexproof.api.auth import get_current_user
from app.lexproof.main import create_app
from app.lexproof.domains.passport.api.router import get_evidence_service


class FakeEvidenceRepository:
    def __init__(self, records):
        self.records = records
        self.writes = []

    def stream(self):
        return iter(self.records)

    def get(self, document_id):
        return {"id": document_id, "owner_id": "user-1"}

    def set(self, document_id, data, merge=False):
        self.writes.append((document_id, data, merge))


def evidence_record(owner_id="user-1", passport_id="ac2ad6e6-d8d7-4408-be19-dcef069fa4df"):
    return {
        "evidence_id": "evidence-1", "passport_id": passport_id, "owner_id": owner_id,
        "evidence_type": "clause", "title": "Risk finding", "description": "A finding",
        "content": "Evidence", "content_type": "text/plain", "risk_impact": 10,
        "compliance_impact": 0, "evidence_status": "valid", "contract_reference": None,
        "policy_reference": None, "analysis_reference": "finding-1",
        "created_at": datetime.now(timezone.utc).isoformat(), "verified_at": None,
        "source": "ai_analysis", "source_id": "finding_1", "hash": "a" * 64, "metadata": {},
    }


def test_evidence_routes_return_records_and_statistics():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    app.dependency_overrides[get_evidence_service] = lambda: __import__(
        "app.lexproof.domains.passport.evidence_service", fromlist=["EvidenceService"]
    ).EvidenceService(FakeEvidenceRepository([evidence_record()]), owner_id="user-1", passport_repository=FakeEvidenceRepository([]))
    client = TestClient(app)
    passport_id = "ac2ad6e6-d8d7-4408-be19-dcef069fa4df"
    evidence = client.get(f"/api/passports/{passport_id}/evidence", headers={"Authorization": "Bearer test"})
    statistics = client.get(f"/api/passports/{passport_id}/evidence/statistics", headers={"Authorization": "Bearer test"})
    assert evidence.status_code == 200
    assert len(evidence.json()) == 1
    assert statistics.status_code == 200
    assert statistics.json()["total_count"] == 1


def test_evidence_routes_require_authentication():
    client = TestClient(create_app())
    passport_id = "ac2ad6e6-d8d7-4408-be19-dcef069fa4df"
    assert client.get(f"/api/passports/{passport_id}/evidence").status_code == 401
    assert client.get(f"/api/passports/{passport_id}/evidence/statistics").status_code == 401


def test_malformed_passport_id_returns_422():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    client = TestClient(app)
    assert client.get("/api/passports/not-a-uuid/evidence", headers={"Authorization": "Bearer test"}).status_code == 422


def test_nonexistent_passport_returns_404(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    app.dependency_overrides[get_evidence_service] = lambda: __import__(
        "app.lexproof.domains.passport.evidence_service", fromlist=["EvidenceService"]
    ).EvidenceService(FakeEvidenceRepository([]), owner_id="user-1", passport_repository=type("Repo", (), {"get": lambda self, _id: None})())
    client = TestClient(app)
    assert client.get("/api/passports/ac2ad6e6-d8d7-4408-be19-dcef069fa4df/evidence", headers={"Authorization": "Bearer test"}).status_code == 404


def test_legacy_evidence_uses_passport_timestamp():
    from app.lexproof.domains.passport.evidence_service import EvidenceService

    legacy = evidence_record()
    legacy.pop("created_at")
    repository = FakeEvidenceRepository([legacy])
    passport_repository = type("Repo", (), {"get": lambda self, _id: {"created_at": "2026-08-24T12:00:00"}})()
    service = EvidenceService(repository, owner_id="user-1", passport_repository=passport_repository)
    import asyncio

    result = asyncio.run(service.get_evidence_by_passport(legacy["passport_id"]))
    assert result[0].created_at.isoformat() == "2026-08-24T12:00:00"
    assert repository.writes


def test_evidence_creation_persists_created_at():
    from app.lexproof.domains.passport.evidence_service import EvidenceService
    from app.lexproof.domains.passport.models import EvidenceItemCreate
    import asyncio

    repository = FakeEvidenceRepository([])
    service = EvidenceService(repository, owner_id="user-1")
    asyncio.run(service.create_evidence_item(
        "passport-1",
        EvidenceItemCreate(
            passport_id="passport-1", evidence_type="clause", title="Finding",
            content="Evidence", content_type="text/plain", source="ai_analysis",
        ),
        user={"uid": "user-1"},
    ))
    assert repository.writes[0][1]["created_at"]


def test_passport_with_zero_evidence_returns_empty_response(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    app.dependency_overrides[get_evidence_service] = lambda: __import__(
        "app.lexproof.domains.passport.evidence_service", fromlist=["EvidenceService"]
    ).EvidenceService(FakeEvidenceRepository([]), owner_id="user-1", passport_repository=FakeEvidenceRepository([]))
    client = TestClient(app)
    passport_id = "ac2ad6e6-d8d7-4408-be19-dcef069fa4df"
    assert client.get(f"/api/passports/{passport_id}/evidence", headers={"Authorization": "Bearer test"}).json() == []
    assert client.get(f"/api/passports/{passport_id}/evidence/statistics", headers={"Authorization": "Bearer test"}).json()["total_count"] == 0