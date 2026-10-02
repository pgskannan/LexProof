import pytest
from fastapi.testclient import TestClient

from app.lexproof.api import trial_requests as tr
from app.lexproof.main import create_app


class FakeRepo:
    def __init__(self):
        self.docs = {}

    def set(self, doc_id, data, merge=False):
        self.docs[doc_id] = data


@pytest.fixture
def client_and_repo(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(tr, "_repository", lambda: repo)
    monkeypatch.setattr(tr, "_limiter", tr._RateLimiter(3, 3600))
    return TestClient(create_app()), repo


VALID = {
    "full_name": "Asha Rao",
    "work_email": "Asha.Rao@Example.com",
    "company": "Acme Procurement",
    "role": "procurement",
    "team_size": "51-200",
    "use_case": "Supplier MSAs",
    "consent": True,
}


def test_valid_request_is_stored(client_and_repo):
    client, repo = client_and_repo
    response = client.post("/api/public/trial-requests", json=VALID)
    assert response.status_code == 201
    assert response.json()["status"] == "received"
    (doc,) = repo.docs.values()
    assert doc["work_email"] == "asha.rao@example.com"
    assert doc["status"] == "new"
    assert "website" not in doc and len(doc["ip_hash"]) == 16


@pytest.mark.parametrize("field,value", [
    ("work_email", "not-an-email"),
    ("role", "hacker"),
    ("team_size", "lots"),
    ("full_name", "A"),
])
def test_invalid_fields_are_rejected(client_and_repo, field, value):
    client, repo = client_and_repo
    response = client.post("/api/public/trial-requests", json={**VALID, field: value})
    assert response.status_code == 422
    assert repo.docs == {}


def test_consent_is_required(client_and_repo):
    client, repo = client_and_repo
    response = client.post("/api/public/trial-requests", json={**VALID, "consent": False})
    assert response.status_code == 422
    assert repo.docs == {}


def test_honeypot_pretends_success_but_stores_nothing(client_and_repo):
    client, repo = client_and_repo
    response = client.post("/api/public/trial-requests", json={**VALID, "website": "http://spam"})
    assert response.status_code == 201
    assert repo.docs == {}


def test_rate_limit(client_and_repo):
    client, _ = client_and_repo
    codes = [client.post("/api/public/trial-requests", json=VALID).status_code for _ in range(4)]
    assert codes == [201, 201, 201, 429]


def test_no_login_needed_and_not_blocked_for_read_only(monkeypatch, client_and_repo):
    monkeypatch.setenv("LEXPROOF_READ_ONLY_UIDS", "demo-judge-1")
    client, _ = client_and_repo
    assert client.post("/api/public/trial-requests", json=VALID).status_code == 201
