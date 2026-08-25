from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
import importlib

passport_router = importlib.import_module("app.lexproof.domains.passport.api.router")

from app.lexproof.api.auth import get_current_user
from app.lexproof.domains.passport.api.router import configure_passport_service
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.main import create_app


class FakeRepository:
    def __init__(self, records=None, failure=None):
        self.records = records or {}
        self.failure = failure

    def get(self, document_id):
        if self.failure:
            raise self.failure
        return self.records.get(document_id)

    def stream(self):
        if self.failure:
            raise self.failure
        return iter(self.records.values())


def passport_record(owner_id="user-1", contract_id="contract-1"):
    return {
        "id": "passport-1", "passport_id": "passport-1", "owner_id": owner_id,
        "contract_id": contract_id, "contract_version": 1,
        "document_hash": "a" * 64, "policy_hash": "b" * 64,
        "analysis_hash": "c" * 64, "evidence_hash": "d" * 64,
        "risk_score": 70, "compliance_score": 80, "policy_version": "default",
        "evidence_count": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": owner_id, "status": "created", "audit_events": [], "metadata": {},
    }


def client_for(repository, monkeypatch):
    service = PassportService(lambda *_: None, "user-1", "user-1", repository=repository)
    configure_passport_service(service)
    monkeypatch.setattr(passport_router, "FirestoreRepository", lambda *_: repository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    return TestClient(app)


def test_passport_exists_returns_200(monkeypatch):
    client = client_for(FakeRepository({"passport-1": passport_record()}), monkeypatch)
    response = client.get("/api/contracts/contract-1/passport?contract_version=1", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200


def test_passport_missing_returns_404(monkeypatch):
    client = client_for(FakeRepository(), monkeypatch)
    response = client.get("/api/contracts/contract-1/passport?contract_version=1", headers={"Authorization": "Bearer test"})
    assert response.status_code == 404


def test_unauthorized_user_returns_401():
    response = TestClient(create_app()).get("/api/contracts/contract-1/passport?contract_version=1")
    assert response.status_code == 401


def test_repository_failure_returns_500(monkeypatch):
    client = client_for(FakeRepository(failure=RuntimeError("repository unavailable")), monkeypatch)
    with pytest.raises(RuntimeError):
        client.get("/api/contracts/contract-1/passport?contract_version=1", headers={"Authorization": "Bearer test"})