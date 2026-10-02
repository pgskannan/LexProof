import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.lexproof.services import auth as auth_module
from app.lexproof.services.auth import READ_ONLY_DETAIL, enforce_read_only, get_current_user


@pytest.fixture(autouse=True)
def judge_is_read_only(monkeypatch):
    monkeypatch.setenv("LEXPROOF_READ_ONLY_UIDS", "demo-judge-1, other-viewer")


def test_reads_are_always_allowed():
    enforce_read_only("demo-judge-1", "GET", "/api/contracts")
    enforce_read_only("demo-judge-1", "HEAD", "/api/contracts")


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/contracts"),
    ("POST", "/api/contracts/c1/analyze"),
    ("POST", "/api/redline-proposals/p1/review"),
    ("PATCH", "/api/contracts/c1/redline-proposals/p1"),
    ("POST", "/api/passports/p1/anchor-root"),
    ("DELETE", "/api/saved-views/v1"),
    ("PATCH", "/api/orgs/lexproof-demo/settings"),
])
def test_writes_are_blocked_for_read_only_accounts(method, path):
    with pytest.raises(HTTPException) as exc:
        enforce_read_only("demo-judge-1", method, path)
    assert exc.value.status_code == 403
    assert exc.value.detail == READ_ONLY_DETAIL


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/orgs/lexproof-demo/ask"),
    ("POST", "/api/findings/translate"),
    ("POST", "/api/passports/p1/verify"),
    ("POST", "/api/contracts/verify-version-history/c1"),
    ("POST", "/api/orgs/lexproof-demo/portfolio-snapshots"),
    ("PATCH", "/api/preferences/ui"),
    ("POST", "/api/notifications/read-all"),
    ("POST", "/api/notifications/n1/read"),
])
def test_read_style_writes_stay_allowed(method, path):
    enforce_read_only("demo-judge-1", method, path)


def test_normal_accounts_are_unaffected():
    enforce_read_only("demo-reviewer-1", "POST", "/api/contracts/c1/analyze")


def test_no_read_only_accounts_configured(monkeypatch):
    monkeypatch.delenv("LEXPROOF_READ_ONLY_UIDS", raising=False)
    enforce_read_only("demo-judge-1", "POST", "/api/contracts")


def test_get_current_user_enforces_read_only(monkeypatch):
    monkeypatch.setattr(auth_module, "verify_firebase_token", lambda token: {"uid": token})
    app = FastAPI()

    @app.get("/api/contracts")
    def read(user=Depends(get_current_user)):
        return {"uid": user["uid"]}

    @app.post("/api/contracts")
    def write(user=Depends(get_current_user)):
        return {"uid": user["uid"]}

    client = TestClient(app)
    assert client.get("/api/contracts", headers={"Authorization": "Bearer demo-judge-1"}).status_code == 200
    blocked = client.post("/api/contracts", headers={"Authorization": "Bearer demo-judge-1"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == READ_ONLY_DETAIL
    assert client.post("/api/contracts", headers={"Authorization": "Bearer demo-owner-1"}).status_code == 200
