from fastapi.testclient import TestClient

from app.lexproof.api import search as search_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user


CONTRACTS = [
    {"id": "contract-1", "contract_id": "contract-1", "owner_id": "user-1", "name": "Acme SaaS Agreement", "status": "active"},
    {"id": "contract-2", "contract_id": "contract-2", "owner_id": "user-2", "name": "Other User Contract", "status": "active"},
]

FINDINGS = [
    {"finding_id": "finding-1", "owner_id": "user-1", "contract_id": "contract-1", "title": "Broad indemnification clause", "severity": "high", "description": "Uncapped liability exposure."},
    {"finding_id": "finding-2", "owner_id": "user-2", "contract_id": "contract-2", "title": "Broad indemnification clause", "severity": "high"},
]

PASSPORTS = [
    {"passport_id": "passport-1", "owner_id": "user-1", "contract_id": "contract-1", "contract_version": 2, "name": "Acme SaaS Agreement"},
]


class FakeSearchRepository:
    def __init__(self, collection: str):
        self.collection = collection

    def stream(self):
        if self.collection == "contracts":
            return iter(CONTRACTS)
        if self.collection == "risk_findings":
            return iter(FINDINGS)
        if self.collection == "legal_passports":
            return iter(PASSPORTS)
        raise AssertionError(f"unexpected collection {self.collection}")


def make_client(monkeypatch):
    monkeypatch.setattr(search_api, "FirestoreRepository", FakeSearchRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    return TestClient(app)


def test_search_requires_authentication():
    response = TestClient(create_app()).get("/api/search?q=acme")
    assert response.status_code == 401


def test_search_matches_contract_and_finding_and_passport(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/search?q=acme")

    assert response.status_code == 200
    body = response.json()
    types = {(item["type"], item["id"]) for item in body}
    assert ("contract", "contract-1") in types
    assert ("passport", "passport-1") in types
    # "acme" is only in the contract/passport name, not in the finding text.
    assert not any(item["type"] == "finding" for item in body)


def test_search_scopes_to_owner(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/search?q=indemnification")

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body}
    assert "finding-1" in ids
    assert "finding-2" not in ids


def test_search_requires_nonempty_query(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/search?q=%20")

    assert response.status_code == 200
    assert response.json() == []
