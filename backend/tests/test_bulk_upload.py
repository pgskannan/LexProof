"""Bulk upload & batch analysis: multi-file upload, per-file isolation."""

import io

from fastapi.testclient import TestClient

from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user


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


class FakeStorage:
    def upload(self, path: str, content: bytes, content_type: str) -> str:
        return f"gs://fake-bucket/{path}"


def make_client(monkeypatch):
    FakeRepository.stores = {"contracts": {}, "contract_versions": {}}
    monkeypatch.setattr(
        contracts_api,
        "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), FakeStorage()),
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    return TestClient(app)


def test_bulk_upload_persists_every_valid_file(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/contracts/bulk",
        files=[
            ("files", ("agreement-1.txt", io.BytesIO(b"Contract one text."), "text/plain")),
            ("files", ("agreement-2.txt", io.BytesIO(b"Contract two text."), "text/plain")),
        ],
    )
    assert response.status_code == 207
    results = response.json()["results"]
    assert len(results) == 2
    assert all(entry["ok"] for entry in results)
    assert len(FakeRepository.stores["contracts"]) == 2
    assert len(FakeRepository.stores["contract_versions"]) == 2


def test_bulk_upload_isolates_one_bad_file(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/contracts/bulk",
        files=[
            ("files", ("good.txt", io.BytesIO(b"Valid contract text."), "text/plain")),
            ("files", ("bad.exe", io.BytesIO(b"not a contract"), "application/octet-stream")),
            ("files", ("also-good.txt", io.BytesIO(b"Another valid contract."), "text/plain")),
        ],
    )
    assert response.status_code == 207
    results = response.json()["results"]
    assert [entry["ok"] for entry in results] == [True, False, True]
    assert results[1]["detail"]
    assert len(FakeRepository.stores["contracts"]) == 2


def test_bulk_upload_rejects_empty_list(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post("/api/contracts/bulk", files=[])
    assert response.status_code in (400, 422)


def test_bulk_upload_rejects_over_limit(monkeypatch):
    client = make_client(monkeypatch)
    files = [("files", (f"agreement-{i}.txt", io.BytesIO(b"Text."), "text/plain")) for i in range(21)]
    response = client.post("/api/contracts/bulk", files=files)
    assert response.status_code == 413


def test_single_upload_still_works_after_refactor(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/contracts",
        files={"file": ("agreement.txt", b"Solo contract text.", "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "uploaded"
    assert FakeRepository.stores["contract_versions"][body["version_id"]]["document_text"] == "Solo contract text."
