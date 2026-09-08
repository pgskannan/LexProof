from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.contract_versions import create_contract_version


class FakeRepository:
    stores: dict[str, dict[str, dict]] = {"contracts": {}, "contract_versions": {}}

    def __init__(self, collection: str):
        self.collection = collection

    def get(self, document_id: str):
        return self.stores[self.collection].get(document_id)

    def set(self, document_id: str, data: dict, merge: bool = False):
        if merge:
            self.stores[self.collection].setdefault(document_id, {}).update(data)
        else:
            self.stores[self.collection][document_id] = dict(data)

    def stream(self):
        return iter({"id": key, **value} for key, value in self.stores[self.collection].items())


def seed_versions():
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {
                "id": "contract-1",
                "owner_id": "owner-1",
                "current_version_id": "version-1",
            }
        },
        "contract_versions": {
            "version-1": {
                "id": "version-1",
                "owner_id": "owner-1",
                "contract_id": "contract-1",
                "version_number": 1,
                "storage_path": "gs://bucket/v1.txt",
                "content_hash": "hash-v1",
                "document_text": "Original contract",
                "analysis_status": "complete",
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
                "custom_metadata": "preserve",
            }
        },
    }


def test_create_version_persists_child_and_preserves_source():
    seed_versions()
    child = create_contract_version(
        "contract-1", "version-1", {"document_text": "Revised contract", "content_hash": "hash-v2"}, "owner-1",
        contracts=FakeRepository("contracts"), versions=FakeRepository("contract_versions"),
    )

    assert child["version_number"] == 2
    assert child["contract_id"] == "contract-1"
    assert child["parent_version_id"] == "version-1"
    assert child["created_by"] == "owner-1"
    assert child["analysis_status"] == "pending"
    assert FakeRepository.stores["contracts"]["contract-1"]["current_version_id"] == child["id"]
    assert FakeRepository.stores["contract_versions"]["version-1"]["document_text"] == "Original contract"
    assert FakeRepository.stores["contract_versions"]["version-1"]["custom_metadata"] == "preserve"


def test_create_version_again_produces_v3():
    seed_versions()
    repository = FakeRepository("contract_versions")
    contracts = FakeRepository("contracts")
    child = create_contract_version("contract-1", "version-1", {}, "owner-1", contracts=contracts, versions=repository)
    grandchild = create_contract_version("contract-1", child["id"], {}, "owner-1", contracts=contracts, versions=repository)

    assert grandchild["version_number"] == 3
    assert grandchild["parent_version_id"] == child["id"]
    assert contracts.get("contract-1")["current_version_id"] == grandchild["id"]
    assert repository.get("version-1")["version_number"] == 1
    assert repository.get(child["id"])["version_number"] == 2


def make_client(monkeypatch, uid: str):
    seed_versions()
    monkeypatch.setattr(contracts_api, "_repositories", lambda: (
        FakeRepository("contracts"), FakeRepository("contract_versions"), object()
    ))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_version_endpoint_requires_owner(monkeypatch):
    client = make_client(monkeypatch, "other-user")
    response = client.post("/api/contracts/contract-1/versions", json={"source_version_id": "version-1"})

    assert response.status_code == 403


def test_version_endpoint_rejects_invalid_contract(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    response = client.post("/api/contracts/missing/versions", json={"source_version_id": "version-1"})

    assert response.status_code == 404


def test_version_endpoint_rejects_invalid_source(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    response = client.post("/api/contracts/contract-1/versions", json={"source_version_id": "missing"})

    assert response.status_code == 404


def test_version_endpoint_creates_v2(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    response = client.post("/api/contracts/contract-1/versions", json={"source_version_id": "version-1"})

    assert response.status_code == 201
    assert response.json()["version_number"] == 2
    assert FakeRepository.stores["contracts"]["contract-1"]["current_version_id"] == response.json()["id"]