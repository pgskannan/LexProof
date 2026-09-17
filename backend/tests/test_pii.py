"""Data security hardening: PII detection/masking utility, security headers, and wiring."""

from fastapi.testclient import TestClient

from app.lexproof.api import contracts as contracts_api
from app.lexproof.api import findings as findings_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.pii import detect_pii, mask_pii


def test_detect_pii_finds_ssn():
    assert detect_pii("The employee's SSN is 123-45-6789 on file.") == ["ssn"]


def test_detect_pii_finds_email():
    assert detect_pii("Contact notices to legal@acmecorp.com.") == ["email"]


def test_detect_pii_finds_credit_card():
    assert "credit_card" in detect_pii("Card on file: 4111 1111 1111 1111 for autopay.")


def test_detect_pii_finds_phone():
    assert "phone" in detect_pii("Reach the account manager at (415) 555-0134.")


def test_detect_pii_returns_empty_for_clean_text():
    assert detect_pii("Liability shall not exceed $10,000 under this Agreement.") == []


def test_detect_pii_handles_none_and_empty():
    assert detect_pii(None) == []
    assert detect_pii("") == []


def test_mask_pii_redacts_ssn_keeping_last_four():
    assert mask_pii("SSN: 123-45-6789") == "SSN: *****6789"


def test_mask_pii_redacts_email_keeping_first_char_and_domain():
    assert mask_pii("Email: john.doe@example.com") == "Email: j***@example.com"


def test_mask_pii_leaves_clean_text_untouched():
    text = "Liability shall not exceed $10,000 under this Agreement."
    assert mask_pii(text) == text


def test_mask_pii_handles_none():
    assert mask_pii(None) is None


def test_security_headers_present_on_every_response():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "strict-transport-security" in response.headers


class FakeRepository:
    stores: dict[str, dict[str, dict]] = {
        "contracts": {},
        "contract_versions": {},
        "legal_passports": {},
        "redline_proposals": {},
        "risk_findings": {},
        "evidence_records": {},
        "evidence_anchors": {},
    }

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
    FakeRepository.stores = {
        "contracts": {},
        "contract_versions": {},
        "legal_passports": {},
        "redline_proposals": {},
        "risk_findings": {},
        "evidence_records": {},
        "evidence_anchors": {},
    }
    monkeypatch.setattr(
        contracts_api,
        "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), FakeStorage()),
    )
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    return TestClient(app)


def test_upload_flags_pii_in_document_text(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/contracts",
        files={"file": ("agreement.txt", b"Employee SSN on file: 123-45-6789.", "text/plain")},
    )
    assert response.status_code == 201
    version = FakeRepository.stores["contract_versions"][response.json()["version_id"]]
    assert version["contains_pii"] is True
    assert "ssn" in version["pii_types"]


def test_upload_no_pii_flag_for_clean_document(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/contracts",
        files={"file": ("agreement.txt", b"Liability shall not exceed $10,000.", "text/plain")},
    )
    assert response.status_code == 201
    version = FakeRepository.stores["contract_versions"][response.json()["version_id"]]
    assert version["contains_pii"] is False
    assert version["pii_types"] == []


def test_versions_endpoint_surfaces_pii_flag(monkeypatch):
    client = make_client(monkeypatch)
    upload = client.post(
        "/api/contracts",
        files={"file": ("agreement.txt", b"Reach us at admin@acme-legal.com for notices.", "text/plain")},
    ).json()

    response = client.get(f"/api/contracts/{upload['contract_id']}/versions")
    assert response.status_code == 200
    [version] = response.json()
    assert version["contains_pii"] is True
    assert "email" in version["pii_types"]
