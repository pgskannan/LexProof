"""Chat notification endpoints: delivery log read, admin-only test-send,
and membership/role enforcement."""

from fastapi.testclient import TestClient

from app.lexproof.api import chat_notifications as chat_notifications_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.chat_notifications import ChatNotificationService
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


def reset_stores():
    FakeRepository.stores = {
        "organizations": {},
        "users": {},
        "organization_invites": {},
        f"organizations/{ORG_ID}/members": {},
        "chat_notification_deliveries": {},
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
    service.ensure_member(ORG_ID, "member-1", ["reviewer"], email="member@example.com")
    return service


def make_client(monkeypatch, uid: str):
    org_service = make_org_service()
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    chat_service = ChatNotificationService(
        organizations=org_service,
        deliveries=FakeRepository("chat_notification_deliveries"),
    )
    monkeypatch.setattr(chat_notifications_api, "get_chat_notification_service", lambda: chat_service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@example.com"}
    return TestClient(app)


def test_test_send_records_a_simulated_delivery_when_unconfigured(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "admin-1")

    response = client.post(f"/api/orgs/{ORG_ID}/chat-notifications/test")
    assert response.status_code == 200
    deliveries = response.json()["deliveries"]
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "simulated"

    listed = client.get(f"/api/orgs/{ORG_ID}/chat-notifications/deliveries").json()["deliveries"]
    assert len(listed) == 1
    assert listed[0]["event_type"] == "test"


def test_test_send_is_admin_only(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "member-1")

    response = client.post(f"/api/orgs/{ORG_ID}/chat-notifications/test")
    assert response.status_code == 403


def test_deliveries_endpoint_requires_org_membership(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "stranger-1")

    assert client.get(f"/api/orgs/{ORG_ID}/chat-notifications/deliveries").status_code == 403
    assert client.post(f"/api/orgs/{ORG_ID}/chat-notifications/test").status_code == 403


def test_deliveries_endpoint_readable_by_any_active_member(monkeypatch):
    reset_stores()
    admin_client = make_client(monkeypatch, "admin-1")
    admin_client.post(f"/api/orgs/{ORG_ID}/chat-notifications/test")

    # A fresh client for a non-admin member, re-pointed at the same
    # (class-level, shared) FakeRepository stores -- a non-admin can read
    # the delivery log even though only an admin can trigger a test send.
    member_client = make_client(monkeypatch, "member-1")
    response = member_client.get(f"/api/orgs/{ORG_ID}/chat-notifications/deliveries")
    assert response.status_code == 200
    assert len(response.json()["deliveries"]) == 1
