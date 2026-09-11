"""CORS tests for the embeddable public-verification widget (Task #108).

The widget runs on a third-party website and calls GET /api/verify/{id}
directly with fetch() from whatever origin embeds it, so that one endpoint
needs a fully open CORS policy even though the rest of the API is
restricted to the configured origin allowlist.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.lexproof.services.ethereum_anchor_service as anchor_service_module
from app.lexproof.main import app
from app.lexproof.repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository

client = TestClient(app)

ARBITRARY_THIRD_PARTY_ORIGIN = "https://a-counterpartys-website.example"


@pytest.fixture
def patched_public_verifier(monkeypatch):
    evidence_store: dict[str, dict] = {}
    anchor_store: dict[str, dict] = {}

    class FakeBlockchain:
        contract_address = "0x1111111111111111111111111111111111111111"

        def verify_evidence(self, evidence_id: str, evidence_hash: bytes) -> bool:
            return False

        def get_evidence_anchor(self, evidence_id: str):
            return None

    monkeypatch.setattr(anchor_service_module, "create_blockchain_service", lambda *a, **k: FakeBlockchain())
    monkeypatch.setattr(EvidenceRecordRepository, "get", lambda self, document_id: evidence_store.get(document_id))
    monkeypatch.setattr(EvidenceAnchorRepository, "get", lambda self, document_id: anchor_store.get(document_id))

    original_singleton = anchor_service_module._ethereum_anchor_service
    anchor_service_module._ethereum_anchor_service = None

    yield {"evidence_store": evidence_store, "anchor_store": anchor_store}

    anchor_service_module._ethereum_anchor_service = original_singleton


def test_public_verify_get_allows_any_origin(patched_public_verifier):
    response = client.get(
        "/api/verify/widget-test-evidence",
        headers={"Origin": ARBITRARY_THIRD_PARTY_ORIGIN},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_public_verify_preflight_options_succeeds(patched_public_verifier):
    response = client.options(
        "/api/verify/widget-test-evidence",
        headers={
            "Origin": ARBITRARY_THIRD_PARTY_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == "*"
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_a_private_endpoint_does_not_get_wildcard_cors(patched_public_verifier):
    # /api/contracts is not on the widget's open-CORS allowlist -- an origin
    # that isn't in cors_origin_list() must not see a wildcard (or any)
    # Access-Control-Allow-Origin header on it, confirming the widened
    # policy above is scoped to the /api/verify/* mount and nothing else.
    response = client.get(
        "/api/contracts",
        headers={"Origin": ARBITRARY_THIRD_PARTY_ORIGIN},
    )

    assert response.headers.get("access-control-allow-origin") != "*"


def test_public_verify_response_still_correct_through_the_mounted_sub_app(patched_public_verifier):
    response = client.get("/api/verify/widget-test-evidence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_id"] == "widget-test-evidence"
    assert payload["status"] == "EVIDENCE_NOT_FOUND"
