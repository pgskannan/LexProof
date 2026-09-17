import copy

from fastapi.testclient import TestClient

from app.lexproof.api import notifications as notifications_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user


class FakeNotificationsRepository:
    def __init__(self, collection: str):
        assert collection == "notifications"

    records: dict[str, dict] = {}

    def stream(self):
        return iter(list(self.records.values()))

    def get(self, notification_id: str):
        return self.records.get(notification_id)

    def set(self, notification_id: str, data: dict, merge: bool = False) -> None:
        if merge and notification_id in self.records:
            self.records[notification_id] = {**self.records[notification_id], **data}
        else:
            self.records[notification_id] = {"id": notification_id, **data}


def make_client(monkeypatch, records=None):
    FakeNotificationsRepository.records = copy.deepcopy(records or {})
    monkeypatch.setattr(notifications_api, "FirestoreRepository", FakeNotificationsRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    return TestClient(app)


BASE_RECORDS = {
    "n1": {"id": "n1", "owner_id": "user-1", "type": "analysis_complete", "title": "Done", "message": "m1", "read": False, "created_at": "2026-09-01T00:00:00+00:00"},
    "n2": {"id": "n2", "owner_id": "user-1", "type": "analysis_failed", "title": "Failed", "message": "m2", "read": True, "created_at": "2026-09-02T00:00:00+00:00"},
    "n3": {"id": "n3", "owner_id": "user-2", "type": "analysis_complete", "title": "Other user", "message": "m3", "read": False, "created_at": "2026-09-03T00:00:00+00:00"},
}


def test_notifications_require_authentication():
    response = TestClient(create_app()).get("/api/notifications")
    assert response.status_code == 401


def test_list_notifications_scoped_to_owner_and_sorted(monkeypatch):
    client = make_client(monkeypatch, BASE_RECORDS)
    response = client.get("/api/notifications")
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == ["n2", "n1"]


def test_unread_only_filter(monkeypatch):
    client = make_client(monkeypatch, BASE_RECORDS)
    response = client.get("/api/notifications?unread_only=true")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["n1"]


def test_unread_count(monkeypatch):
    client = make_client(monkeypatch, BASE_RECORDS)
    response = client.get("/api/notifications/unread-count")
    assert response.status_code == 200
    assert response.json() == {"count": 1}


def test_mark_read(monkeypatch):
    client = make_client(monkeypatch, BASE_RECORDS)
    response = client.post("/api/notifications/n1/read")
    assert response.status_code == 200
    assert response.json()["read"] is True
    assert client.get("/api/notifications/unread-count").json() == {"count": 0}


def test_mark_read_rejects_other_users_notification(monkeypatch):
    client = make_client(monkeypatch, BASE_RECORDS)
    response = client.post("/api/notifications/n3/read")
    assert response.status_code == 404


def test_mark_all_read(monkeypatch):
    client = make_client(monkeypatch, BASE_RECORDS)
    response = client.post("/api/notifications/read-all")
    assert response.status_code == 200
    assert response.json() == {"updated": 1}
    assert client.get("/api/notifications/unread-count").json() == {"count": 0}


# --- Notification preferences ---------------------------------------------

from tests.fakes import FakeRepository  # noqa: E402


def make_prefs_client(monkeypatch, uid: str = "user-1"):
    FakeRepository.stores = {"notification_preferences": {}}
    monkeypatch.setattr(notifications_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_preferences_require_authentication():
    response = TestClient(create_app()).get("/api/notifications/preferences")
    assert response.status_code == 401


def test_get_preferences_defaults_to_in_app_on_email_off(monkeypatch):
    client = make_prefs_client(monkeypatch)
    response = client.get("/api/notifications/preferences")
    assert response.status_code == 200
    assert response.json() == {
        "in_app_analysis_complete": True,
        "in_app_analysis_failed": True,
        "email_analysis_complete": False,
        "email_analysis_failed": False,
    }


def test_update_preferences_persists_and_round_trips(monkeypatch):
    client = make_prefs_client(monkeypatch)
    response = client.patch(
        "/api/notifications/preferences",
        json={"in_app_analysis_complete": False, "email_analysis_failed": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["in_app_analysis_complete"] is False
    assert body["email_analysis_failed"] is True
    # Untouched fields keep their defaults.
    assert body["in_app_analysis_failed"] is True
    assert body["email_analysis_complete"] is False

    # And persists across a fresh GET.
    reread = client.get("/api/notifications/preferences")
    assert reread.json() == body


def test_update_preferences_scoped_per_user(monkeypatch):
    FakeRepository.stores = {"notification_preferences": {}}
    monkeypatch.setattr(notifications_api, "FirestoreRepository", FakeRepository)
    app = create_app()

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-a"}
    client_a = TestClient(app)
    client_a.patch("/api/notifications/preferences", json={"in_app_analysis_complete": False})

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-b"}
    client_b = TestClient(app)
    response_b = client_b.get("/api/notifications/preferences")
    # user-b never changed anything, so still sees the default.
    assert response_b.json()["in_app_analysis_complete"] is True
