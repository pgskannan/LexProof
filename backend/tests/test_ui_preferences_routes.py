import copy

from fastapi.testclient import TestClient

from app.lexproof.api import ui_preferences as ui_preferences_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user

DEFAULT_WIDGETS = [
    {"id": "stat-contracts", "visible": True},
    {"id": "stat-passports", "visible": True},
    {"id": "stat-findings", "visible": True},
    {"id": "recent-activity", "visible": True},
]
DEFAULT_BODY = {"theme": "system", "dashboard_widgets": DEFAULT_WIDGETS, "tour_completed": False}


class FakeUiPreferencesRepository:
    def __init__(self, collection: str):
        assert collection == "ui_preferences"

    records: dict[str, dict] = {}

    def get(self, user_id: str):
        return self.records.get(user_id)

    def set(self, user_id: str, data: dict, merge: bool = False) -> None:
        if merge and user_id in self.records:
            self.records[user_id] = {**self.records[user_id], **data}
        else:
            self.records[user_id] = dict(data)


def make_client(monkeypatch, records=None, uid="user-1"):
    FakeUiPreferencesRepository.records = copy.deepcopy(records or {})
    monkeypatch.setattr(ui_preferences_api, "FirestoreRepository", FakeUiPreferencesRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_preferences_require_authentication():
    response = TestClient(create_app()).get("/api/preferences/ui")
    assert response.status_code == 401


def test_get_defaults_to_system_theme_and_default_widgets(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/preferences/ui")
    assert response.status_code == 200
    assert response.json() == DEFAULT_BODY


def test_patch_persists_and_round_trips(monkeypatch):
    client = make_client(monkeypatch)
    response = client.patch("/api/preferences/ui", json={"theme": "dark"})
    assert response.status_code == 200
    assert response.json() == {**DEFAULT_BODY, "theme": "dark"}
    assert client.get("/api/preferences/ui").json()["theme"] == "dark"


def test_patch_rejects_invalid_theme_value_by_ignoring_it(monkeypatch):
    client = make_client(monkeypatch)
    client.patch("/api/preferences/ui", json={"theme": "dark"})
    response = client.patch("/api/preferences/ui", json={"theme": "not-a-real-theme"})
    assert response.status_code == 200
    assert response.json()["theme"] == "dark"


def test_preferences_scoped_per_user(monkeypatch):
    shared_records: dict[str, dict] = {}
    client_a = make_client(monkeypatch, shared_records, uid="user-a")
    FakeUiPreferencesRepository.records = shared_records
    client_a.patch("/api/preferences/ui", json={"theme": "dark"})

    client_b = make_client(monkeypatch, FakeUiPreferencesRepository.records, uid="user-b")
    response_b = client_b.get("/api/preferences/ui")
    assert response_b.json()["theme"] == "system"


def test_patch_reorders_and_hides_widgets(monkeypatch):
    client = make_client(monkeypatch)
    reordered = [
        {"id": "recent-activity", "visible": True},
        {"id": "stat-findings", "visible": False},
        {"id": "stat-contracts", "visible": True},
        {"id": "stat-passports", "visible": True},
    ]
    response = client.patch("/api/preferences/ui", json={"dashboard_widgets": reordered})
    assert response.status_code == 200
    assert response.json()["dashboard_widgets"] == reordered
    assert client.get("/api/preferences/ui").json()["dashboard_widgets"] == reordered


def test_patch_widget_layout_scoped_per_user(monkeypatch):
    shared_records: dict[str, dict] = {}
    client_a = make_client(monkeypatch, shared_records, uid="user-a")
    FakeUiPreferencesRepository.records = shared_records
    hidden_findings = [
        {"id": "stat-contracts", "visible": True},
        {"id": "stat-passports", "visible": True},
        {"id": "stat-findings", "visible": False},
        {"id": "recent-activity", "visible": True},
    ]
    client_a.patch("/api/preferences/ui", json={"dashboard_widgets": hidden_findings})

    client_b = make_client(monkeypatch, FakeUiPreferencesRepository.records, uid="user-b")
    response_b = client_b.get("/api/preferences/ui")
    assert response_b.json()["dashboard_widgets"] == DEFAULT_WIDGETS


def test_patch_marks_tour_completed_and_round_trips(monkeypatch):
    client = make_client(monkeypatch)
    assert client.get("/api/preferences/ui").json()["tour_completed"] is False
    response = client.patch("/api/preferences/ui", json={"tour_completed": True})
    assert response.status_code == 200
    assert response.json()["tour_completed"] is True
    assert client.get("/api/preferences/ui").json()["tour_completed"] is True


def test_tour_completed_scoped_per_user(monkeypatch):
    shared_records: dict[str, dict] = {}
    client_a = make_client(monkeypatch, shared_records, uid="user-a")
    FakeUiPreferencesRepository.records = shared_records
    client_a.patch("/api/preferences/ui", json={"tour_completed": True})

    client_b = make_client(monkeypatch, FakeUiPreferencesRepository.records, uid="user-b")
    assert client_b.get("/api/preferences/ui").json()["tour_completed"] is False
