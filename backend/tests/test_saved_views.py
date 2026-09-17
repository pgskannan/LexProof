"""Unit tests for per-user saved filter views (Contracts / Findings list
pages): auth, owner scoping, page scoping, the per-page cap, and delete
ownership enforcement."""

import copy

from fastapi.testclient import TestClient

from app.lexproof.api import saved_views as saved_views_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from tests.fakes import FakeRepository


def make_client(monkeypatch, uid: str = "user-1", records=None):
    FakeRepository.stores = {"saved_views": copy.deepcopy(records or {})}
    monkeypatch.setattr(saved_views_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_requires_authentication():
    response = TestClient(create_app()).get("/api/saved-views?page=contracts")
    assert response.status_code == 401


def test_list_requires_page_query_param(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/saved-views")
    assert response.status_code == 422


def test_create_and_list_round_trip(monkeypatch):
    client = make_client(monkeypatch)
    created = client.post(
        "/api/saved-views",
        json={"page": "contracts", "name": "High risk only", "filters": {"risk_level": "high"}},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "High risk only"
    assert body["filters"] == {"risk_level": "high"}

    listed = client.get("/api/saved-views?page=contracts")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


def test_views_scoped_by_page(monkeypatch):
    client = make_client(monkeypatch)
    client.post("/api/saved-views", json={"page": "contracts", "name": "A", "filters": {}})
    client.post("/api/saved-views", json={"page": "findings", "name": "B", "filters": {}})
    contracts_views = client.get("/api/saved-views?page=contracts").json()
    findings_views = client.get("/api/saved-views?page=findings").json()
    assert [v["name"] for v in contracts_views] == ["A"]
    assert [v["name"] for v in findings_views] == ["B"]


def test_views_scoped_by_owner(monkeypatch):
    FakeRepository.stores = {"saved_views": {}}
    monkeypatch.setattr(saved_views_api, "FirestoreRepository", FakeRepository)
    app = create_app()

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-a"}
    TestClient(app).post("/api/saved-views", json={"page": "contracts", "name": "Mine", "filters": {}})

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-b"}
    response_b = TestClient(app).get("/api/saved-views?page=contracts")
    assert response_b.json() == []


def test_delete_removes_view(monkeypatch):
    client = make_client(monkeypatch)
    created = client.post("/api/saved-views", json={"page": "contracts", "name": "Temp", "filters": {}}).json()
    delete_response = client.delete(f"/api/saved-views/{created['id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/saved-views?page=contracts").json() == []


def test_delete_rejects_other_users_view(monkeypatch):
    FakeRepository.stores = {"saved_views": {}}
    monkeypatch.setattr(saved_views_api, "FirestoreRepository", FakeRepository)
    app = create_app()

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-a"}
    created = TestClient(app).post("/api/saved-views", json={"page": "contracts", "name": "Mine", "filters": {}}).json()

    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-b"}
    response = TestClient(app).delete(f"/api/saved-views/{created['id']}")
    assert response.status_code == 404


def test_per_page_cap_enforced(monkeypatch):
    client = make_client(monkeypatch)
    for index in range(25):
        response = client.post("/api/saved-views", json={"page": "contracts", "name": f"V{index}", "filters": {}})
        assert response.status_code == 201
    over_cap = client.post("/api/saved-views", json={"page": "contracts", "name": "One too many", "filters": {}})
    assert over_cap.status_code == 400
