"""Tests for the Slack/Teams chat notification service (services/chat_notifications.py)."""

from app.lexproof.services.chat_notifications import ChatNotificationService
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

ORG_ID = "org-1"


class FakeResponse:
    def __init__(self, status_code: int, text: str = "ok"):
        self.status_code = status_code
        self.text = text


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
    service.create_org("Acme Legal", "user-1", org_id=ORG_ID, creator_email="admin@acme.test")
    return service


def make_chat_service(*, http_post=None, organizations=None) -> ChatNotificationService:
    return ChatNotificationService(
        organizations=organizations or make_org_service(),
        deliveries=FakeRepository("chat_notification_deliveries"),
        http_post=http_post,
    )


def test_notify_org_simulates_when_no_webhook_configured():
    reset_stores()
    service = make_chat_service()
    records = service.notify_org(ORG_ID, event_type="test", title="Hello", message="World")
    assert len(records) == 1
    assert records[0]["status"] == "simulated"
    assert records[0]["provider"] == "stub"
    assert records[0]["channel"] == "none_configured"
    assert "World" in records[0]["message"]


def test_notify_org_sends_real_webhook_when_configured():
    reset_stores()
    orgs = make_org_service()
    orgs.update_org_settings(ORG_ID, {"slack_webhook_url": "https://hooks.slack.com/services/xyz"}, "user-1")
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return FakeResponse(200)

    service = make_chat_service(http_post=fake_post, organizations=orgs)
    records = service.notify_org(ORG_ID, event_type="workflow_overdue", title="Overdue", message="Please act")
    assert len(records) == 1
    assert records[0]["status"] == "sent"
    assert records[0]["channel"] == "slack"
    assert len(calls) == 1
    assert calls[0][0] == "https://hooks.slack.com/services/xyz"
    assert "Overdue" in calls[0][1]["text"]
    assert "Please act" in calls[0][1]["text"]


def test_notify_org_sends_to_both_channels_when_both_configured():
    reset_stores()
    orgs = make_org_service()
    orgs.update_org_settings(
        ORG_ID,
        {
            "slack_webhook_url": "https://hooks.slack.com/services/xyz",
            "teams_webhook_url": "https://outlook.office.com/webhook/abc",
        },
        "user-1",
    )
    calls = []

    def fake_post(url, payload):
        calls.append(url)
        return FakeResponse(200)

    service = make_chat_service(http_post=fake_post, organizations=orgs)
    records = service.notify_org(ORG_ID, event_type="test", title="Hi", message="There")
    assert len(records) == 2
    assert {record["channel"] for record in records} == {"slack", "teams"}
    assert all(record["status"] == "sent" for record in records)
    assert len(calls) == 2


def test_notify_org_records_failure_on_non_2xx_without_raising():
    reset_stores()
    orgs = make_org_service()
    orgs.update_org_settings(ORG_ID, {"slack_webhook_url": "https://hooks.slack.com/services/bad"}, "user-1")

    def fake_post(url, payload):
        return FakeResponse(404, text="no_service")

    service = make_chat_service(http_post=fake_post, organizations=orgs)
    records = service.notify_org(ORG_ID, event_type="test", title="Hi", message="There")
    assert records[0]["status"] == "failed"
    assert "404" in records[0]["detail"]


def test_notify_org_records_failure_on_exception_without_raising():
    reset_stores()
    orgs = make_org_service()
    orgs.update_org_settings(ORG_ID, {"slack_webhook_url": "https://hooks.slack.com/services/bad"}, "user-1")

    def raising_post(url, payload):
        raise ConnectionError("boom")

    service = make_chat_service(http_post=raising_post, organizations=orgs)
    records = service.notify_org(ORG_ID, event_type="test", title="Hi", message="There")
    assert records[0]["status"] == "failed"
    assert "boom" in records[0]["detail"]


def test_list_deliveries_scopes_to_org_sorts_desc_and_respects_limit():
    reset_stores()
    orgs = make_org_service()
    orgs.create_org("Other Org", "user-2", org_id="org-2", creator_email="admin@other.test")
    service = make_chat_service(organizations=orgs)
    for index in range(3):
        service.notify_org(ORG_ID, event_type="test", title=f"T{index}", message="m")
    service.notify_org("org-2", event_type="test", title="Other", message="m")

    results = service.list_deliveries(ORG_ID, limit=2)
    assert len(results) == 2
    assert all(record["org_id"] == ORG_ID for record in results)
    assert results[0]["title"] == "T2"  # newest first


def test_update_org_settings_rejects_non_https_webhook_url():
    reset_stores()
    orgs = make_org_service()
    try:
        orgs.update_org_settings(ORG_ID, {"slack_webhook_url": "http://insecure.example.com"}, "user-1")
        assert False, "expected an error for a non-https webhook URL"
    except Exception as error:
        assert "https" in str(error)


def test_update_org_settings_clears_webhook_url_with_empty_string():
    reset_stores()
    orgs = make_org_service()
    orgs.update_org_settings(ORG_ID, {"slack_webhook_url": "https://hooks.slack.com/services/xyz"}, "user-1")
    settings = orgs.update_org_settings(ORG_ID, {"slack_webhook_url": ""}, "user-1")
    assert settings["slack_webhook_url"] is None
