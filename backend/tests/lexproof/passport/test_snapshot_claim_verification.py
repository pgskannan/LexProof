"""Claimed snapshot inputs must fail closed; unclaimed legacy inputs stay compatible."""

from __future__ import annotations

import hashlib
import json

import pytest

from app.lexproof.domains.passport.integrity import verify_passport_integrity
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.domains.passport.utils.hashing import (
    compute_passport_hash,
    hash_evidence_package,
)


def _analysis_engine():
    async def engine(_document: str, _policy: str) -> dict:
        return {
            "risk_score": 35,
            "risk_level": "medium",
            "compliance_score": 85,
            "findings": [{
                "title": "Finding 1",
                "severity": "high",
                "description": "Finding description",
                "evidence": "Evidence text",
                "recommendation": "Recommendation text",
                "risk_impact": 95,
                "compliance_impact": 15,
                "source_section": "Section 1",
                "evidence_quote": "Quote text",
            }],
            "key_clauses": ["Section 1"],
            "compliance_items": ["Policy"],
        }

    return engine


async def _create_passport():
    service = PassportService(_analysis_engine(), user_id="user", tenant_id="tenant")
    passport = await service.create_passport(
        contract_id="contract-claim-verify",
        contract_version=1,
        policy_version="policy-1",
        document_content="Sample contract text",
        normalized_document="sample contract text",
        policy_content="Sample policy",
    )
    evidence_items = await service.get_evidence(passport.passport_id)
    return passport.model_dump(mode="json"), evidence_items


def _independent_passport_hash(document_hash: str, policy_hash: str, analysis_hash: str, evidence_hash: str) -> str:
    payload = {
        "analysis_hash": analysis_hash,
        "document_hash": document_hash,
        "evidence_hash": evidence_hash,
        "passport_hash_algorithm": "sha256",
        "policy_hash": policy_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
async def test_valid_complete_snapshot_passes():
    data, evidence_items = await _create_passport()
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["document_status"] == "PASS"
    assert result["policy_status"] == "PASS"
    assert result["analysis_status"] == "PASS"
    assert result["evidence_status"] == "PASS"
    assert result["passport_hash_status"] == "PASS"
    assert result["document_verified"] is True
    assert result["verified"] is True


@pytest.mark.asyncio
async def test_claimed_document_content_null_fails():
    data, evidence_items = await _create_passport()
    data["metadata"]["verification_snapshot"]["document_content"] = None
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["document_status"] == "FAIL"
    assert result["document_verified"] is False
    assert result["verified"] is False
    assert result["policy_status"] == "PASS"
    assert result["passport_hash_status"] == "PASS"


@pytest.mark.asyncio
async def test_claimed_policy_content_null_fails():
    data, evidence_items = await _create_passport()
    data["metadata"]["verification_snapshot"]["policy_content"] = None
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["policy_status"] == "FAIL"
    assert result["policy_verified"] is False
    assert result["verified"] is False
    assert result["document_status"] == "PASS"


@pytest.mark.asyncio
async def test_claimed_analysis_result_unusable_fails():
    data, evidence_items = await _create_passport()
    data["metadata"]["verification_snapshot"]["analysis_result"] = None
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["analysis_status"] == "FAIL"
    assert result["analysis_verified"] is False
    assert result["verified"] is False
    assert result["document_status"] == "PASS"


@pytest.mark.asyncio
async def test_claimed_evidence_items_null_fails_instead_of_live_fallback():
    data, evidence_items = await _create_passport()
    data["metadata"]["verification_snapshot"]["evidence_items"] = None
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["evidence_status"] == "FAIL"
    assert result["evidence_verified"] is False
    assert result["verified"] is False


@pytest.mark.asyncio
async def test_evidence_only_repaired_snapshot_stays_compatible():
    data, evidence_items = await _create_passport()
    data["metadata"]["verification_snapshot"] = {
        "evidence_items": data["metadata"]["verification_snapshot"]["evidence_items"],
    }
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["evidence_status"] == "PASS"
    assert result["evidence_verified"] is True
    assert result["document_status"] == "UNVERIFIABLE"
    assert result["policy_status"] == "UNVERIFIABLE"
    assert result["analysis_status"] == "UNVERIFIABLE"
    assert result["document_verified"] is False
    assert result["policy_verified"] is False
    assert result["analysis_verified"] is False
    assert result["passport_hash_status"] == "PASS"
    assert result["verified"] is True


def test_legacy_passport_without_snapshot_stays_compatible():
    document_hash = "d" * 64
    policy_hash = "e" * 64
    analysis_hash = "f" * 64
    evidence_hash = "g" * 64
    data = {
        "document_hash": document_hash,
        "policy_hash": policy_hash,
        "analysis_hash": analysis_hash,
        "evidence_hash": evidence_hash,
        "metadata": {
            "passport_hash": _independent_passport_hash(
                document_hash, policy_hash, analysis_hash, evidence_hash
            ),
        },
    }
    result = verify_passport_integrity(data)

    assert result["document_status"] == "UNVERIFIABLE"
    assert result["policy_status"] == "UNVERIFIABLE"
    assert result["analysis_status"] == "UNVERIFIABLE"
    assert result["evidence_status"] == "UNVERIFIABLE"
    assert result["document_verified"] is False
    assert result["evidence_verified"] is False
    assert result["passport_hash_status"] == "PASS"
    assert result["passport_hash_verified"] is True
    assert result["verified"] is True


def test_legacy_live_evidence_without_snapshot_evidence_items_still_checks_package():
    item = {
        "evidence_id": "e1",
        "passport_id": "legacy-passport",
        "evidence_type": "clause",
        "title": "e1",
        "description": "",
        "content": "clause text",
        "content_type": "text/plain",
        "risk_impact": 10,
        "compliance_impact": 10,
        "evidence_status": "valid",
        "contract_reference": "",
        "policy_reference": "",
        "analysis_reference": "",
        "source": "test",
        "source_id": "e1",
        "metadata": {},
    }
    evidence_hash = hash_evidence_package([item])
    data = {
        "document_hash": "d" * 64,
        "policy_hash": "e" * 64,
        "analysis_hash": "f" * 64,
        "evidence_hash": evidence_hash,
        "created_at": "2026-01-01T00:00:00+00:00",
        "metadata": {
            "passport_hash": compute_passport_hash("d" * 64, "e" * 64, "f" * 64, evidence_hash),
            "verification_snapshot": {},
        },
    }
    result = verify_passport_integrity(data, evidence_items=[item])
    assert result["evidence_status"] == "PASS"
    assert result["document_status"] == "UNVERIFIABLE"
    assert result["verified"] is True

    tampered = [{**item, "title": "tampered"}]
    failed = verify_passport_integrity(data, evidence_items=tampered)
    assert failed["evidence_status"] == "FAIL"
    assert failed["verified"] is False


@pytest.mark.asyncio
async def test_stored_component_hash_changes_fail_passport_root_and_component():
    data, evidence_items = await _create_passport()
    expected_root = _independent_passport_hash(
        data["document_hash"],
        data["policy_hash"],
        data["analysis_hash"],
        data["evidence_hash"],
    )
    assert data["metadata"]["passport_hash"] == expected_root

    original = verify_passport_integrity(data, evidence_items=evidence_items)
    assert original["passport_hash_verified"] is True
    assert original["document_status"] == "PASS"

    data["document_hash"] = "c" * 64
    result = verify_passport_integrity(data, evidence_items=evidence_items)
    assert result["document_status"] == "FAIL"
    assert result["document_verified"] is False
    assert result["passport_hash_status"] == "FAIL"
    assert result["passport_hash_verified"] is False
    assert result["verified"] is False


@pytest.mark.asyncio
async def test_snapshot_tamper_fails_component_but_stored_passport_root_still_binds():
    data, evidence_items = await _create_passport()
    data["metadata"]["verification_snapshot"]["document_content"] = "Tampered contract text"
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["document_status"] == "FAIL"
    assert result["document_verified"] is False
    assert result["passport_hash_status"] == "PASS"
    assert result["passport_hash_verified"] is True
    assert result["verified"] is False


@pytest.mark.asyncio
async def test_changing_each_stored_component_hash_fails():
    data, evidence_items = await _create_passport()
    for field in ("document_hash", "policy_hash", "analysis_hash", "evidence_hash"):
        mutated = json.loads(json.dumps(data))
        mutated[field] = "a" * 64
        result = verify_passport_integrity(mutated, evidence_items=evidence_items)
        assert result["verified"] is False
        assert result["passport_hash_verified"] is False
        assert result[f"{field.removesuffix('_hash')}_verified"] is False


@pytest.mark.asyncio
async def test_changing_stored_passport_hash_fails_root_only():
    data, evidence_items = await _create_passport()
    data["metadata"]["passport_hash"] = "e" * 64
    result = verify_passport_integrity(data, evidence_items=evidence_items)

    assert result["document_status"] == "PASS"
    assert result["policy_status"] == "PASS"
    assert result["analysis_status"] == "PASS"
    assert result["evidence_status"] == "PASS"
    assert result["passport_hash_status"] == "FAIL"
    assert result["passport_hash_verified"] is False
    assert result["verified"] is False
