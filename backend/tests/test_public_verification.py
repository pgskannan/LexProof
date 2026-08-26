"""Tests for the public evidence verification endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.lexproof.services.ethereum_anchor_service as anchor_service_module
from app.lexproof.domains.passport.utils.hashing import hash_evidence_item
from app.lexproof.main import app
from app.lexproof.repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository

client = TestClient(app)


@pytest.fixture
def patched_public_verifier(monkeypatch):
    """Patch the blockchain client and Firestore repository reads with in-memory fakes."""
    evidence_store: dict[str, dict] = {}
    anchor_store: dict[str, dict] = {}

    class FakeBlockchain:
        contract_address = "0x1111111111111111111111111111111111111111"

        def verify_evidence(self, evidence_id: str, evidence_hash: bytes) -> bool:
            anchor = anchor_store.get(evidence_id)
            if not anchor:
                return False
            expected = anchor["evidence_hash"]
            if expected.startswith("0x"):
                expected = expected[2:]
            return bytes.fromhex(expected) == evidence_hash

        def get_evidence_anchor(self, evidence_id: str):
            anchor = anchor_store.get(evidence_id)
            if not anchor:
                return None
            return {"evidence_hash": anchor["evidence_hash"]}

    def fake_create_blockchain_service(*args, **kwargs):
        return FakeBlockchain()

    monkeypatch.setattr(anchor_service_module, "create_blockchain_service", fake_create_blockchain_service)
    monkeypatch.setattr(EvidenceRecordRepository, "get", lambda self, document_id: evidence_store.get(document_id))
    monkeypatch.setattr(EvidenceAnchorRepository, "get", lambda self, document_id: anchor_store.get(document_id))

    original_singleton = anchor_service_module._ethereum_anchor_service
    anchor_service_module._ethereum_anchor_service = None

    yield {"evidence_store": evidence_store, "anchor_store": anchor_store}

    anchor_service_module._ethereum_anchor_service = original_singleton


def test_public_verifier_evidence_not_found_returns_200(patched_public_verifier):
    response = client.get("/api/verify/missing-evidence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_id"] == "missing-evidence"
    assert payload["verified"] is False
    assert payload["status"] == "EVIDENCE_NOT_FOUND"


def test_public_verifier_anchor_not_found_returns_200(patched_public_verifier):
    evidence = {
        "evidence_id": "evd-2",
        "passport_id": "passport-2",
        "evidence_type": "CLAUSE",
        "title": "Original title",
        "content": "This contract clause is still original.",
        "description": "Clause description",
        "source": "contract",
    }
    patched_public_verifier["evidence_store"]["evd-2"] = evidence

    response = client.get("/api/verify/evd-2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is False
    assert payload["status"] == "ANCHOR_NOT_FOUND"
    assert payload["computed_hash"] == hash_evidence_item(evidence)


def test_public_verifier_matching_hash_returns_verified(patched_public_verifier):
    evidence = {
        "evidence_id": "evd-3",
        "passport_id": "passport-3",
        "evidence_type": "CLAUSE",
        "title": "In-force clause",
        "content": "This clause has not changed.",
        "description": "Stable evidence",
        "source": "contract",
    }
    computed_hash = hash_evidence_item(evidence)
    patched_public_verifier["evidence_store"]["evd-3"] = evidence
    patched_public_verifier["anchor_store"]["evd-3"] = {
        "evidence_id": "evd-3",
        "evidence_hash": computed_hash,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": "0x1111111111111111111111111111111111111111",
        "transaction_hash": "0x" + "aa" * 32,
        "block_number": 123456,
        "anchored_at": "2025-01-15T12:00:00+00:00",
    }

    response = client.get("/api/verify/evd-3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is True
    assert payload["status"] == "VERIFIED"
    assert payload["computed_hash"] == computed_hash
    assert payload["evidence_hash_on_chain"] == computed_hash
    assert payload["blockchain_network"] == "ethereum-sepolia"


def test_public_verifier_tampered_evidence_returns_tampered(patched_public_verifier):
    original = {
        "evidence_id": "evd-4",
        "passport_id": "passport-4",
        "evidence_type": "CLAUSE",
        "title": "Original title",
        "content": "The original clause text.",
        "description": "This is what was anchored",
        "source": "contract",
    }
    mutated = {
        **original,
        "content": "The clause text was altered after anchoring.",
    }
    on_chain_hash = hash_evidence_item(original)
    patched_public_verifier["evidence_store"]["evd-4"] = mutated
    patched_public_verifier["anchor_store"]["evd-4"] = {
        "evidence_id": "evd-4",
        "evidence_hash": on_chain_hash,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": "0x1111111111111111111111111111111111111111",
        "transaction_hash": "0x" + "bb" * 32,
        "block_number": 456789,
        "anchored_at": "2025-01-15T12:00:00+00:00",
    }

    response = client.get("/api/verify/evd-4")

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is False
    assert payload["status"] == "TAMPERED"
    assert payload["computed_hash"] != payload["evidence_hash_on_chain"]
    assert payload["computed_hash"] == hash_evidence_item(mutated)
    assert payload["evidence_hash_on_chain"] == on_chain_hash


def test_public_verifier_blank_evidence_id_returns_404(patched_public_verifier):
    response = client.get("/api/verify/")
    assert response.status_code == 404


def test_public_verifier_legacy_route_does_not_exist(patched_public_verifier):
    response = client.get("/verify/evd-legacy")
    assert response.status_code == 404


def test_public_verifier_response_contains_expected_fields(patched_public_verifier):
    evidence = {
        "evidence_id": "evd-5",
        "passport_id": "passport-5",
        "evidence_type": "CLAUSE",
        "title": "Immutable clause",
        "content": "These facts have been anchored.",
        "description": "Expected response fields",
        "source": "contract",
    }
    on_chain_hash = hash_evidence_item(evidence)
    patched_public_verifier["evidence_store"]["evd-5"] = evidence
    patched_public_verifier["anchor_store"]["evd-5"] = {
        "evidence_id": "evd-5",
        "evidence_hash": on_chain_hash,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": "0x1111111111111111111111111111111111111111",
        "transaction_hash": "0x" + "cc" * 32,
        "block_number": 987654,
        "anchored_at": "2025-01-15T12:00:00+00:00",
    }

    response = client.get("/api/verify/evd-5")

    assert response.status_code == 200
    payload = response.json()
    expected_fields = {
        "evidence_id",
        "verified",
        "status",
        "evidence_hash_on_chain",
        "computed_hash",
        "blockchain_network",
        "contract_address",
        "transaction_hash",
        "block_number",
        "anchored_at",
        "timestamp",
    }
    assert expected_fields.issubset(payload.keys())
    assert payload["status"] == "VERIFIED"
    assert payload["verified"] is True


def test_public_verifier_does_not_leak_sensitive_evidence_fields(patched_public_verifier):
    evidence = {
        "evidence_id": "evd-6",
        "passport_id": "passport-6",
        "evidence_type": "CLAUSE",
        "title": "Secret title",
        "content": "Top secret clause content.",
        "description": "Sensitive details",
        "source": "contract",
        "risk_impact": "HIGH",
        "compliance_impact": "HIGH",
    }
    on_chain_hash = hash_evidence_item(evidence)
    patched_public_verifier["evidence_store"]["evd-6"] = evidence
    patched_public_verifier["anchor_store"]["evd-6"] = {
        "evidence_id": "evd-6",
        "evidence_hash": on_chain_hash,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": "0x1111111111111111111111111111111111111111",
        "transaction_hash": "0x" + "dd" * 32,
        "block_number": 333333,
        "anchored_at": "2025-01-15T12:00:00+00:00",
    }

    response = client.get("/api/verify/evd-6")

    assert response.status_code == 200
    payload = response.json()
    assert "title" not in payload
    assert "content" not in payload
    assert "document_content" not in payload
    assert "risk_score" not in payload
    assert "compliance_score" not in payload
    assert "evidence_content" not in payload
