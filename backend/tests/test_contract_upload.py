"""Multi-format ingestion & OCR: extension/type coverage and OCR fallback behavior."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user


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
    # list_contract_versions also constructs legal_passports/redline_proposals
    # repositories directly (not via _repositories()); fake those too so the
    # endpoint doesn't reach for real Firestore credentials in tests.
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    return TestClient(app)


def _sample_image_bytes(text: str = "HELLO OCR") -> bytes:
    image = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 30), text, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _blank_pdf_bytes() -> bytes:
    """A single-page PDF with no embedded text, to exercise the scanned-PDF fallback."""
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def _text_pdf_bytes(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


# -- _extract_text unit coverage -------------------------------------------------


def test_extract_text_plain_txt_is_not_applicable():
    text, ocr_status = contracts_api._extract_text("agreement.txt", b"Hello, world.")
    assert text == "Hello, world."
    assert ocr_status == "not_applicable"


def test_extract_text_native_pdf_skips_ocr():
    pdf_bytes = _text_pdf_bytes("This Master Services Agreement is entered into by the parties.")
    text, ocr_status = contracts_api._extract_text("agreement.pdf", pdf_bytes)
    assert "Master Services Agreement" in text
    assert ocr_status == "native_text"


def test_extract_text_scanned_pdf_falls_back_to_ocr():
    pdf_bytes = _blank_pdf_bytes()
    text, ocr_status = contracts_api._extract_text("scanned.pdf", pdf_bytes)
    # A blank page OCRs to empty/near-empty text but the engine did run.
    assert ocr_status in {"ocr_success", "ocr_unavailable"}
    assert isinstance(text, str)


def test_extract_text_scanned_pdf_without_tesseract_binary_is_graceful(monkeypatch):
    monkeypatch.setattr(contracts_api, "_ocr_engine_available", lambda: False)
    pdf_bytes = _blank_pdf_bytes()
    text, ocr_status = contracts_api._extract_text("scanned.pdf", pdf_bytes)
    assert ocr_status == "ocr_unavailable"
    assert "OCR pending" in text


@pytest.mark.skipif(
    not contracts_api._ocr_engine_available(),
    reason="Tesseract OCR binary is not installed",
)
def test_extract_text_image_runs_real_ocr():
    image_bytes = _sample_image_bytes("HELLO OCR")
    text, ocr_status = contracts_api._extract_text("scan.png", image_bytes)
    assert ocr_status == "ocr_success"
    assert "HELLO" in text.upper()


def test_extract_text_image_without_tesseract_binary_is_graceful(monkeypatch):
    monkeypatch.setattr(contracts_api, "_ocr_engine_available", lambda: False)
    image_bytes = _sample_image_bytes()
    text, ocr_status = contracts_api._extract_text("scan.jpg", image_bytes)
    assert ocr_status == "ocr_unavailable"
    assert "OCR pending" in text
    assert "Tesseract" in text


# -- upload endpoint coverage -----------------------------------------------------


def test_upload_accepts_png_image(monkeypatch):
    client = make_client(monkeypatch)
    image_bytes = _sample_image_bytes("CONTRACT SCAN")
    response = client.post(
        "/api/contracts",
        files={"file": ("scan.png", image_bytes, "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    version = FakeRepository.stores["contract_versions"][body["version_id"]]
    if contracts_api._ocr_engine_available():
        assert version["ocr_status"] == "ocr_success"
        assert "CONTRACT" in version["document_text"].upper()
    else:
        assert version["ocr_status"] == "ocr_unavailable"


def test_upload_stamps_org_id_from_header(monkeypatch):
    """POST /api/contracts without X-Org-Id used to persist a contract with no
    org_id. ProposalService.create() then raises PermissionError('Contract is
    not assigned to an organization') -- the full-lifecycle E2E's Save proposal
    failure. When the client sends the current org, stamp it on the contract
    and version so workflow can start."""
    client = make_client(monkeypatch)
    monkeypatch.setattr(
        contracts_api,
        "load_org_member",
        lambda org_id, user: {**user, "org_id": org_id},
    )
    response = client.post(
        "/api/contracts",
        files={"file": ("agreement.txt", b"The total liability cap for any claim is $100,000.", "text/plain")},
        headers={"X-Org-Id": "lexproof-demo"},
    )
    assert response.status_code == 201
    body = response.json()
    assert FakeRepository.stores["contracts"][body["contract_id"]]["org_id"] == "lexproof-demo"
    assert FakeRepository.stores["contract_versions"][body["version_id"]]["org_id"] == "lexproof-demo"


def test_upload_without_org_header_does_not_invent_an_org(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/contracts",
        files={"file": ("agreement.txt", b"Hello, world.", "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert "org_id" not in FakeRepository.stores["contracts"][body["contract_id"]]


def test_upload_accepts_tiff_extension_and_reports_ocr_status_when_unavailable(monkeypatch):
    monkeypatch.setattr(contracts_api, "_ocr_engine_available", lambda: False)
    client = make_client(monkeypatch)
    image_bytes = _sample_image_bytes()
    buffer = io.BytesIO()
    Image.open(io.BytesIO(image_bytes)).save(buffer, format="TIFF")
    response = client.post(
        "/api/contracts",
        files={"file": ("scan.tiff", buffer.getvalue(), "image/tiff")},
    )
    assert response.status_code == 201
    version = FakeRepository.stores["contract_versions"][response.json()["version_id"]]
    assert version["ocr_status"] == "ocr_unavailable"


def test_upload_rejects_unsupported_extension(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/contracts",
        files={"file": ("agreement.exe", b"not a contract", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_list_versions_surfaces_ocr_status(monkeypatch):
    client = make_client(monkeypatch)
    image_bytes = _sample_image_bytes("TERMS AND CONDITIONS")
    upload = client.post(
        "/api/contracts",
        files={"file": ("scan.png", image_bytes, "image/png")},
    ).json()

    response = client.get(f"/api/contracts/{upload['contract_id']}/versions")

    assert response.status_code == 200
    [version] = response.json()
    if contracts_api._ocr_engine_available():
        assert version["ocr_status"] == "ocr_success"
    else:
        assert version["ocr_status"] == "ocr_unavailable"
