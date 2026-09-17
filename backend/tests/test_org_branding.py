"""White-label / custom branding tests (Task #109).

Covers two surfaces: (1) org Admins setting/clearing a logo_url and
primary_color via the existing org-settings endpoint, with the same
https://-only / valid-hex validation style already used for the chat
webhook URLs, and (2) that branding being safely exposed on the
counterparty external-access view, where the counterparty is exactly the
intended external audience for an org's own name/logo/color.
"""

from fastapi.testclient import TestClient

from app.lexproof.api import counterparty as counterparty_api
from app.lexproof.api import organizations as org_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository
from tests.test_counterparty_links import (
    ORG_ID as COUNTERPARTY_ORG_ID,
    _create_link,
    make_client as make_counterparty_client,
)

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


def test_branding_defaults_to_unset(monkeypatch):
    client, _service = make_client(monkeypatch, "admin-1")
    response = client.get(f"/api/orgs/{ORG_ID}/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["logo_url"] is None
    assert body["primary_color"] is None


def test_admin_can_set_branding_and_it_persists(monkeypatch):
    client, service = make_client(monkeypatch, "admin-1")
    response = client.patch(
        f"/api/orgs/{ORG_ID}/settings",
        json={"logo_url": "https://cdn.example.com/acme-logo.png", "primary_color": "#7c3aed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["logo_url"] == "https://cdn.example.com/acme-logo.png"
    assert body["primary_color"] == "#7c3aed"

    refetched = client.get(f"/api/orgs/{ORG_ID}/settings")
    assert refetched.json()["logo_url"] == "https://cdn.example.com/acme-logo.png"
    assert refetched.json()["primary_color"] == "#7c3aed"
    assert service.get_org_settings(ORG_ID)["primary_color"] == "#7c3aed"


def test_branding_rejects_non_https_logo_url(monkeypatch):
    client, _service = make_client(monkeypatch, "admin-1")
    response = client.patch(
        f"/api/orgs/{ORG_ID}/settings", json={"logo_url": "http://insecure.example.com/logo.png"}
    )
    assert response.status_code == 400
    assert "https://" in response.json()["detail"]


def test_branding_rejects_invalid_hex_color(monkeypatch):
    client, _service = make_client(monkeypatch, "admin-1")
    for bad_color in ["blue", "#fff", "#12345g", "2563eb"]:
        response = client.patch(f"/api/orgs/{ORG_ID}/settings", json={"primary_color": bad_color})
        assert response.status_code == 400, bad_color
        assert "hex color" in response.json()["detail"]


def test_branding_can_be_cleared_with_empty_string(monkeypatch):
    client, _service = make_client(monkeypatch, "admin-1")
    client.patch(
        f"/api/orgs/{ORG_ID}/settings",
        json={"logo_url": "https://cdn.example.com/logo.png", "primary_color": "#7c3aed"},
    )
    cleared = client.patch(f"/api/orgs/{ORG_ID}/settings", json={"logo_url": "", "primary_color": ""})
    assert cleared.status_code == 200
    body = cleared.json()
    assert body["logo_url"] is None
    assert body["primary_color"] is None


def test_reviewer_can_read_but_not_write_branding(monkeypatch):
    client, _service = make_client(monkeypatch, "reviewer-1", "reviewer@example.com")
    read = client.get(f"/api/orgs/{ORG_ID}/settings")
    assert read.status_code == 200
    write = client.patch(f"/api/orgs/{ORG_ID}/settings", json={"primary_color": "#7c3aed"})
    assert write.status_code == 403


def test_counterparty_external_view_includes_org_branding(monkeypatch):
    client, service = make_counterparty_client(monkeypatch, "owner-1")
    service.organizations.update_org_settings(
        COUNTERPARTY_ORG_ID,
        {"logo_url": "https://cdn.example.com/acme-logo.png", "primary_color": "#7c3aed", "name": "Acme Legal"},
        "admin-1",
    )
    token = _create_link(client).json()["token"]
    monkeypatch.setattr(counterparty_api, "_service", lambda: service)
    public = TestClient(create_app())
    response = public.get(f"/api/external/{token}")
    assert response.status_code == 200
    body = response.json()
    assert body["org_name"] == "Acme Legal"
    assert body["org_logo_url"] == "https://cdn.example.com/acme-logo.png"
    assert body["org_primary_color"] == "#7c3aed"


def test_counterparty_external_view_branding_defaults_to_none(monkeypatch):
    client, service = make_counterparty_client(monkeypatch, "owner-1")
    token = _create_link(client).json()["token"]
    monkeypatch.setattr(counterparty_api, "_service", lambda: service)
    public = TestClient(create_app())
    response = public.get(f"/api/external/{token}")
    assert response.status_code == 200
    body = response.json()
    assert body["org_name"] == "LexProof Demo"
    assert body["org_logo_url"] is None
    assert body["org_primary_color"] is None
