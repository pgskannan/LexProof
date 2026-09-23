"""HTTP-level integration tests for the additive passport-root anchoring API
surface (docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md §16, §22, §23):

  * POST /api/passports/{id}/anchor-root  (new, authenticated)
  * POST /api/passports/{id}/verify        (extended with anchor_status)
  * GET  /api/verify/passport/{id}         (public, existence-only)
  * POST /api/passports/{id}/anchor        (legacy route -- now permanently 410)

These exercise the real FastAPI app/router wiring (auth dependency,
path/response models, exception-to-HTTP-status mapping) via TestClient,
mirroring the existing tests/test_p1b_..._verify_fallback.py technique:
FakeRepository-backed passport/evidence services plus a scripted
PassportRootAnchorService substituted at the router's own import name, so
these tests prove the ROUTER's wiring rather than re-testing
PassportRootAnchorService's own internal logic (already covered by
tests/lexproof/passport/test_passport_root_anchor_service.py).
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.lexproof.domains.passport.evidence_service import EvidenceService
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.passport_root_anchor_service import (
    PassportEligibilityError,
    PassportRootConflictError,
)
from tests.fakes import FakeRepository

passport_router = importlib.import_module("app.lexproof.domains.passport.api.router")
blockchain_api = importlib.import_module("app.lexproof.api.blockchain")
passport_root_anchor_service = importlib.import_module(
    "app.lexproof.services.passport_root_anchor_service"
)

OWNER = "owner-1"
PASSPORT_ID = None  # set per-test via fixture


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def passport_record(passport_id: str, contract_id: str, owner_id: str) -> dict:
    return {
        "id": passport_id,
        "passport_id": passport_id,
        "owner_id": owner_id,
        "contract_id": contract_id,
        "contract_version": 1,
        "document_hash": "a" * 64,
        "policy_hash": "b" * 64,
        "analysis_hash": "c" * 64,
        "evidence_hash": "d" * 64,
        "risk_score": 70,
        "compliance_score": 80,
        "policy_version": "default",
        "evidence_count": 0,
        "created_at": _now(),
        "created_by": owner_id,
        "status": "created",
        "audit_events": [],
        "metadata": {},
    }


@pytest.fixture
def api_fixture(monkeypatch):
    passport_id = str(uuid4())
    contract_id = str(uuid4())

    FakeRepository.stores = {
        "organizations": {},
        "users": {},
        "organization_invites": {},
        "contracts": {contract_id: {"id": contract_id, "owner_id": OWNER}},
        "legal_passports": {passport_id: passport_record(passport_id, contract_id, OWNER)},
        "evidence_records": {},
        "passport_anchors": {},
    }

    def _passport_service_for(uid: str) -> PassportService:
        return PassportService(
            analysis_engine=lambda *_: None,
            user_id=uid,
            tenant_id=uid,
            repository=FakeRepository("legal_passports"),
            contracts_repository=FakeRepository("contracts"),
        )

    def _evidence_service_for(uid: str) -> EvidenceService:
        return EvidenceService(
            FakeRepository("evidence_records"),
            owner_id=uid,
            passport_repository=FakeRepository("legal_passports"),
            anchor_repository=FakeRepository("evidence_anchors"),
            contracts_repository=FakeRepository("contracts"),
        )

    async def _get_evidence_service(user):
        return _evidence_service_for(str(user["uid"]))

    monkeypatch.setattr(passport_router, "get_read_passport_service", lambda user: _passport_service_for(str(user["uid"])))
    monkeypatch.setattr(passport_router, "get_evidence_service", _get_evidence_service)
    monkeypatch.setattr(passport_router, "FirestoreRepository", FakeRepository)

    return {"passport_id": passport_id, "contract_id": contract_id}


def eligible_integrity(passport_hash: str = "e" * 64) -> dict:
    return {
        "document_status": "PASS",
        "policy_status": "PASS",
        "analysis_status": "PASS",
        "evidence_status": "PASS",
        "passport_hash_status": "PASS",
        "recomputed_passport_hash": passport_hash,
    }


class ScriptedAnchorService:
    """A fully scripted stand-in for PassportRootAnchorService, substituted
    at the router's own `get_passport_root_anchor_service` import name --
    proves the ROUTER's request/response/exception wiring, independent of
    the anchor service's own (separately, exhaustively unit-tested) logic."""

    def __init__(self, *, anchor_result=None, anchor_exception=None, verify_result=None, public_result=None):
        self.anchor_result = anchor_result
        self.anchor_exception = anchor_exception
        self.verify_result = verify_result
        self.public_result = public_result
        self.anchor_calls: list[dict] = []
        self.verify_calls: list[str] = []
        self.public_calls: list[tuple] = []

    async def anchor_passport_root(self, passport_id, passport_doc, integrity, *, actor_id=None, org_id=None):
        self.anchor_calls.append({
            "passport_id": passport_id,
            "actor_id": actor_id,
            "org_id": org_id,
            "integrity": integrity,
        })
        if self.anchor_exception:
            raise self.anchor_exception
        return self.anchor_result

    async def verify_passport_root_status(self, passport_id, integrity):
        self.verify_calls.append(passport_id)
        return self.verify_result if self.verify_result is not None else {**integrity, "anchor_status": "NOT_ANCHORED"}

    async def public_root_existence(self, passport_id, passport_hash):
        self.public_calls.append((passport_id, passport_hash))
        return self.public_result


def _install_scripted_service(monkeypatch, service: ScriptedAnchorService, *, on_router=True, on_public=False):
    if on_router:
        monkeypatch.setattr(passport_router, "get_passport_root_anchor_service", lambda **kwargs: service)
    if on_public:
        monkeypatch.setattr(passport_root_anchor_service, "get_passport_root_anchor_service", lambda **kwargs: service)


def _client(uid: str = OWNER) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/passports/{id}/anchor-root
# ---------------------------------------------------------------------------


def test_anchor_root_success_returns_anchor_record(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    anchor_record = {"passport_id": api_fixture["passport_id"], "passport_hash": "e" * 64, "transaction_hash": "0x" + "a" * 64}
    service = ScriptedAnchorService(anchor_result=anchor_record)
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    assert response.json() == anchor_record
    assert len(service.anchor_calls) == 1
    assert service.anchor_calls[0]["actor_id"] == OWNER
    assert service.anchor_calls[0]["passport_id"] == api_fixture["passport_id"]
    assert service.anchor_calls[0]["integrity"]["recomputed_passport_hash"] == "e" * 64


def test_anchor_root_eligibility_error_maps_to_409_with_reasons(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    exc = PassportEligibilityError(api_fixture["passport_id"], eligible_integrity(), ["evidence_status=FAIL"])
    service = ScriptedAnchorService(anchor_exception=exc)
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 409
    assert response.json()["detail"]["reasons"] == ["evidence_status=FAIL"]


def test_anchor_root_conflict_error_maps_to_409(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    service = ScriptedAnchorService(anchor_exception=PassportRootConflictError("already has a different anchored root"))
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 409
    assert "different anchored root" in response.json()["detail"]


def test_anchor_root_not_configured_error_maps_to_503(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    service = ScriptedAnchorService(
        anchor_exception=ValueError("ETHEREUM_PASSPORT_REGISTRY_ADDRESS is not configured")
    )
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 503


def test_anchor_root_generic_value_error_maps_to_400(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    service = ScriptedAnchorService(anchor_exception=ValueError("passport_id must be between 1 and 256 characters"))
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 400


def test_anchor_root_runtime_error_maps_to_503(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    service = ScriptedAnchorService(anchor_exception=RuntimeError("chain unreachable"))
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 503


def test_anchor_root_unexpected_exception_maps_to_500(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    service = ScriptedAnchorService(anchor_exception=KeyError("boom"))
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 500


def test_anchor_root_requires_authentication(api_fixture):
    app = create_app()
    client = TestClient(app)
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root")
    assert response.status_code == 401


def test_anchor_root_returns_404_for_invisible_passport_without_calling_anchor_service(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    service = ScriptedAnchorService(anchor_result={"should": "never-be-returned"})
    _install_scripted_service(monkeypatch, service)

    client = _client(uid="complete-stranger")
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/anchor-root", headers={"Authorization": "Bearer test"})

    assert response.status_code == 404
    assert service.anchor_calls == []


# ---------------------------------------------------------------------------
# POST /api/passports/{id}/verify (extended with anchor_status)
# ---------------------------------------------------------------------------


def test_verify_endpoint_merges_anchor_status_into_response(api_fixture, monkeypatch):
    integrity = eligible_integrity()
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: integrity)
    service = ScriptedAnchorService(verify_result={**integrity, "anchor_status": "PASS", "on_chain_root": "e" * 64})
    _install_scripted_service(monkeypatch, service)

    client = _client()
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/verify", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    body = response.json()
    assert body["anchor_status"] == "PASS"
    assert body["passport_hash_status"] == "PASS"
    assert service.verify_calls == [api_fixture["passport_id"]]


def test_verify_endpoint_404_for_invisible_passport(api_fixture, monkeypatch):
    monkeypatch.setattr(passport_router, "verify_passport_integrity", lambda doc, evidence_items=None: eligible_integrity())
    service = ScriptedAnchorService(verify_result={"anchor_status": "PASS"})
    _install_scripted_service(monkeypatch, service)

    client = _client(uid="complete-stranger")
    response = client.post(f"/api/passports/{api_fixture['passport_id']}/verify", headers={"Authorization": "Bearer test"})

    assert response.status_code == 404
    assert service.verify_calls == []


# ---------------------------------------------------------------------------
# GET /api/verify/passport/{id} (public, existence-only)
# ---------------------------------------------------------------------------


def test_public_root_existence_endpoint_no_auth_required(monkeypatch):
    passport_id = str(uuid4())
    service = ScriptedAnchorService(public_result={
        "exists": True,
        "status": "ANCHORED",
        "blockchain_network": "ethereum-sepolia",
        "contract_address": "0x0000000000000000000000000000000000000002",
        "chain_id": 11155111,
    })
    _install_scripted_service(monkeypatch, service, on_router=False, on_public=True)

    app = create_app()
    client = TestClient(app)
    response = client.get(f"/api/verify/passport/{passport_id}", params={"passport_hash": "e" * 64})

    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is True
    assert body["status"] == "ANCHORED"
    assert body["passport_id"] == passport_id
    assert service.public_calls == [(passport_id, "e" * 64)]


def test_public_root_existence_endpoint_not_anchored(monkeypatch):
    passport_id = str(uuid4())
    service = ScriptedAnchorService(public_result={"exists": False, "status": "NOT_ANCHORED"})
    _install_scripted_service(monkeypatch, service, on_router=False, on_public=True)

    app = create_app()
    client = TestClient(app)
    response = client.get(f"/api/verify/passport/{passport_id}", params={"passport_hash": "e" * 64})

    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["status"] == "NOT_ANCHORED"


def test_public_root_existence_endpoint_never_exposes_confidential_fields(monkeypatch):
    """The public response model itself is the enforcement point: even if
    the service returned extra keys, PassportRootPublicVerificationResult
    only serializes its declared fields."""
    passport_id = str(uuid4())
    service = ScriptedAnchorService(public_result={
        "exists": True,
        "status": "ANCHORED",
        "document_status": "PASS",
        "recomputed_passport_hash": "should-never-leak",
    })
    _install_scripted_service(monkeypatch, service, on_router=False, on_public=True)

    app = create_app()
    client = TestClient(app)
    response = client.get(f"/api/verify/passport/{passport_id}", params={"passport_hash": "e" * 64})

    body = response.json()
    assert "document_status" not in body
    assert "recomputed_passport_hash" not in body


# ---------------------------------------------------------------------------
# POST /api/passports/{id}/anchor (legacy -- permanently disabled)
# ---------------------------------------------------------------------------


def test_legacy_anchor_route_permanently_returns_410(monkeypatch):
    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("legacy anchor route must never touch create_blockchain_service")

    monkeypatch.setattr(blockchain_api, "create_blockchain_service", _must_not_be_called)

    client = _client()
    response = client.post(f"/api/passports/{uuid4()}/anchor", json={}, headers={"Authorization": "Bearer test"})

    assert response.status_code == 410
    assert "anchor-root" in response.json()["detail"]


def test_legacy_anchor_route_requires_authentication():
    app = create_app()
    client = TestClient(app)
    response = client.post(f"/api/passports/{uuid4()}/anchor", json={})
    assert response.status_code == 401


def test_legacy_anchor_route_rejects_arbitrary_client_supplied_fields(monkeypatch):
    """Even if a caller still sends the OLD request shape (client-supplied
    hashes/scores), the disabled handler takes no body at all and returns
    410 regardless of what is posted -- proving those fields are simply
    never read, not merely ignored deep inside old logic."""
    client = _client()
    response = client.post(
        f"/api/passports/{uuid4()}/anchor",
        json={
            "contract_hash": "a" * 64,
            "policy_hash": "b" * 64,
            "analysis_hash": "c" * 64,
            "evidence_hash": "d" * 64,
            "risk_score": 100,
            "compliance_score": 0,
        },
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 410
