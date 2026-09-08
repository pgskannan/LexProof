"""Organization membership and org-scoped auth tests."""

from fastapi.testclient import TestClient

from app.lexproof.api import organizations as org_api
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
    }


def make_service() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def make_client(monkeypatch, uid: str, email: str = "admin@example.com"):
    reset_stores()
    service = make_service()
    service.create_org("LexProof Demo", "admin-1", org_id=ORG_ID, creator_email="admin@example.com")
    service.ensure_member(ORG_ID, "reviewer-1", ["reviewer"], email="reviewer@example.com")
    monkeypatch.setattr(org_api, "_orgs", lambda: service)
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": email}
    return TestClient(app), service


def test_admin_can_list_and_invite_members(monkeypatch):
    client, service = make_client(monkeypatch, "admin-1")
    listed = client.get(f"/api/orgs/{ORG_ID}/members")
    assert listed.status_code == 200
    invited = client.post(
        f"/api/orgs/{ORG_ID}/members/invites",
        json={"email": "approver@example.com", "roles": ["approver"]},
    )
    assert invited.status_code == 201
    accepted = service.sync_signed_in_user("approver-1", "approver@example.com", "Approver")
    assert any(org["org_id"] == ORG_ID for org in accepted["orgs"])
    member = service.get_active_member(ORG_ID, "approver-1")
    assert member is not None
    assert member["roles"] == ["approver"]
    assert member["status"] == "active"


def test_reviewer_cannot_manage_members(monkeypatch):
    client, _service = make_client(monkeypatch, "reviewer-1", "reviewer@example.com")
    listed = client.get(f"/api/orgs/{ORG_ID}/members")
    assert listed.status_code == 403
    invited = client.post(
        f"/api/orgs/{ORG_ID}/members/invites",
        json={"email": "other@example.com", "roles": ["auditor"]},
    )
    assert invited.status_code == 403


def test_non_member_is_forbidden(monkeypatch):
    client, _service = make_client(monkeypatch, "stranger-1", "stranger@example.com")
    response = client.get(f"/api/orgs/{ORG_ID}/members")
    assert response.status_code == 403
    assert "active member" in response.json()["detail"].lower()


def test_me_returns_memberships(monkeypatch):
    client, _service = make_client(monkeypatch, "admin-1", "admin@example.com")
    response = client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "admin-1"
    assert body["orgs"][0]["org_id"] == ORG_ID
    assert "admin" in body["orgs"][0]["roles"]


def test_get_org_settings_returns_defaults(monkeypatch):
    client, _service = make_client(monkeypatch, "admin-1")
    response = client.get(f"/api/orgs/{ORG_ID}/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["default_link_expiry_days"] == 14
    assert body["notify_on_assignment"] is True


def test_non_admin_member_can_read_but_not_write_settings(monkeypatch):
    client, _service = make_client(monkeypatch, "reviewer-1", "reviewer@example.com")
    read = client.get(f"/api/orgs/{ORG_ID}/settings")
    assert read.status_code == 200
    write = client.patch(f"/api/orgs/{ORG_ID}/settings", json={"default_link_expiry_days": 30})
    assert write.status_code == 403


def test_admin_can_update_settings_and_it_persists(monkeypatch):
    client, service = make_client(monkeypatch, "admin-1")
    response = client.patch(
        f"/api/orgs/{ORG_ID}/settings",
        json={"name": "Acme Legal", "default_link_expiry_days": 30, "notify_on_assignment": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Acme Legal"
    assert body["default_link_expiry_days"] == 30
    assert body["notify_on_assignment"] is False

    refetched = client.get(f"/api/orgs/{ORG_ID}/settings")
    assert refetched.json()["default_link_expiry_days"] == 30
    assert service.get_org(ORG_ID)["name"] == "Acme Legal"


def test_settings_reject_out_of_range_expiry(monkeypatch):
    client, _service = make_client(monkeypatch, "admin-1")
    response = client.patch(f"/api/orgs/{ORG_ID}/settings", json={"default_link_expiry_days": 999})
    assert response.status_code == 422
