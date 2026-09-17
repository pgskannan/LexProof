"""Portfolio trend analytics endpoints: org-scoped read/capture, membership
enforcement."""

from fastapi.testclient import TestClient

from app.lexproof.api import portfolio as portfolio_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


def reset_stores():
    FakeRepository.stores = {
        "organizations": {},
        "users": {},
        "organization_invites": {},
        f"organizations/{ORG_ID}/members": {},
        "portfolio_snapshots": {},
        "contracts": {
            "c1": {"id": "c1", "name": "Acme MSA", "org_id": ORG_ID},
            "c2": {"id": "c2", "name": "Other Org Contract", "org_id": "someone-else"},
        },
        "risk_findings": {
            "f1": {"id": "f1", "contract_id": "c1", "severity": "critical"},
            "f-other-org": {"id": "f-other-org", "contract_id": "c2", "severity": "critical"},
        },
        "redline_proposals": {},
        "legal_passports": {},
    }


def make_org_service() -> OrganizationService:
    service = OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )
    service.create_org("LexProof Demo", "admin-1", org_id=ORG_ID, creator_email="admin@example.com")
    return service


def make_client(monkeypatch, uid: str):
    org_service = make_org_service()
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    monkeypatch.setattr(portfolio_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": "admin@example.com"}
    return TestClient(app)


def test_capture_then_list_round_trips_a_real_snapshot(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "admin-1")

    capture_response = client.post(f"/api/orgs/{ORG_ID}/portfolio-snapshots")
    assert capture_response.status_code == 200
    captured = capture_response.json()
    assert captured["org_id"] == ORG_ID
    assert captured["contract_count"] == 1
    assert captured["findings_total"] == 1  # f1 only -- f-other-org excluded

    list_response = client.get(f"/api/orgs/{ORG_ID}/portfolio-snapshots")
    assert list_response.status_code == 200
    snapshots = list_response.json()["snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0]["snapshot_id"] == captured["snapshot_id"]


def test_capturing_twice_the_same_day_does_not_duplicate(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "admin-1")

    client.post(f"/api/orgs/{ORG_ID}/portfolio-snapshots")
    client.post(f"/api/orgs/{ORG_ID}/portfolio-snapshots")

    snapshots = client.get(f"/api/orgs/{ORG_ID}/portfolio-snapshots").json()["snapshots"]
    assert len(snapshots) == 1


def test_portfolio_snapshot_endpoints_require_org_membership(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "stranger-1")

    assert client.get(f"/api/orgs/{ORG_ID}/portfolio-snapshots").status_code == 403
    assert client.post(f"/api/orgs/{ORG_ID}/portfolio-snapshots").status_code == 403
