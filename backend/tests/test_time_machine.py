"""Contract Time Machine history must be owner-scoped and must not block on chain I/O."""

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.lexproof.domains.passport.service import _is_visible_to_tenant
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user

CONTRACT_ID = "797b61c9-4d50-41f6-b095-078561545fbd"


def _passport(version: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        passport_id=f"passport-{version}",
        contract_version=version,
        document_hash="d" * 64,
        policy_hash="e" * 64,
        analysis_hash="f" * 64,
        evidence_hash="g" * 64,
        risk_score=12.0,
        compliance_score=88.0,
        policy_version="policy-1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={
            "clauses": [
                {
                    "text": f"Clause {version}",
                    "hash": "a" * 64,
                    "clause_id": f"c{version}",
                    "risk_score": 12,
                    "compliance_score": 88,
                }
            ]
        },
    )


def test_read_only_tenant_hides_owned_passports():
    assert _is_visible_to_tenant({"owner_id": "owner-1"}, "owner-1") is True
    assert _is_visible_to_tenant({"owner_id": "owner-1"}, "read-only") is False


def test_history_returns_owner_passports_without_calling_chain(monkeypatch):
    passport = _passport(1)

    class FakeService:
        async def list_passports(self, contract_id=None, limit=20, offset=0):
            assert contract_id == CONTRACT_ID
            return [SimpleNamespace(passport_id=passport.passport_id)]

        async def get_passport(self, passport_id):
            assert passport_id == passport.passport_id
            return passport

    def fake_read(user):
        assert user["uid"] == "owner-1"
        return FakeService()

    monkeypatch.setattr("app.lexproof.api.time_machine.get_read_passport_service", fake_read)
    monkeypatch.setattr(
        "app.lexproof.api.time_machine.create_blockchain_service",
        lambda: (_ for _ in ()).throw(AssertionError("history must not call chain")),
    )

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    response = TestClient(app).get(f"/api/time-machine/history/{CONTRACT_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_id"] == CONTRACT_ID
    assert len(body["versions"]) == 1
    assert body["versions"][0]["passport_id"] == "passport-1"
    assert body["versions"][0]["blockchain_proof_verified"] is False


def test_compare_does_not_call_chain(monkeypatch):
    first, second = _passport(1), _passport(2)
    by_id = {first.passport_id: first, second.passport_id: second}

    class FakeService:
        async def list_passports(self, contract_id=None, limit=20, offset=0):
            return [SimpleNamespace(passport_id=first.passport_id), SimpleNamespace(passport_id=second.passport_id)]

        async def get_passport(self, passport_id):
            return by_id[passport_id]

    monkeypatch.setattr("app.lexproof.api.time_machine.get_read_passport_service", lambda user: FakeService())
    monkeypatch.setattr(
        "app.lexproof.api.time_machine.create_blockchain_service",
        lambda: (_ for _ in ()).throw(AssertionError("compare must not call chain")),
    )

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    response = TestClient(app).get(
        "/api/time-machine/compare",
        params={"contract_id": CONTRACT_ID, "version_from": 1, "version_to": 2},
    )
    assert response.status_code == 200
    assert response.json()["blockchain_proof_verified"] is False
