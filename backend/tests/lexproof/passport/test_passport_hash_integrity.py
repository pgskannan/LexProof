"""Integrity tests for passport fingerprints and evidence mappings."""

import hashlib
import json
import re

import pytest

from app.lexproof.domains.passport.evidence_service import EvidenceService
from app.lexproof.domains.passport.models import EvidenceItemSummary
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.domains.passport.utils.hashing import compute_passport_hash
from app.lexproof.domains.passport.validation import validate_analysis_response


def test_passport_hash_is_deterministic_sha256_and_covers_all_inputs():
    inputs = {
        "document_hash": "document-a",
        "policy_hash": "policy-a",
        "analysis_hash": "analysis-a",
        "evidence_hash": "evidence-a",
    }

    first = compute_passport_hash(**inputs)
    second = compute_passport_hash(**inputs)

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    canonical_inputs = {
        "document_hash": "document-a",
        "policy_hash": "policy-a",
        "analysis_hash": "analysis-a",
        "evidence_hash": "evidence-a",
        "passport_hash_algorithm": "sha256",
    }
    assert first == hashlib.sha256(
        json.dumps(canonical_inputs, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    for field in inputs:
        changed = {**inputs, field: f"{inputs[field]}-changed"}
        assert compute_passport_hash(**changed) != first


@pytest.mark.asyncio
async def test_evidence_preserves_ai_impacts():
    """Test that evidence items preserve risk_impact and compliance_impact from AI analysis."""
    async def analysis_engine(_document: str, _policy: str) -> dict:
        return {
            "risk_score": 85,
            "risk_level": "high",
            "compliance_score": 0,
            "findings": [
                {
                    "title": "AI value",
                    "severity": "high",
                    "description": "Test finding with values",
                    "evidence": "Evidence text",
                    "recommendation": "Recommendation text",
                    "risk_impact": 42.5,
                    "compliance_impact": 7.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
                {
                    "title": "AI zero",
                    "severity": "medium",
                    "description": "Test finding with zero values",
                    "evidence": "Evidence text",
                    "recommendation": "Recommendation text",
                    "risk_impact": 0,
                    "compliance_impact": 0,
                    "source_section": "Section 2",
                    "evidence_quote": "Quote text 2",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["General"],
        }

    service = PassportService(analysis_engine, user_id="user", tenant_id="user")
    passport = await service.create_passport("contract", 1, "default", "text")
    evidence = await service.get_evidence(passport.passport_id)

    assert evidence[0]["risk_impact"] == 42.5
    assert evidence[0]["compliance_impact"] == 7.0
    assert evidence[1]["risk_impact"] == 0
    assert evidence[1]["compliance_impact"] == 0


@pytest.mark.asyncio
async def test_evidence_preserves_source_section_and_evidence_quote():
    """Test that evidence items preserve source_section and evidence_quote from AI analysis."""
    async def analysis_engine(_document: str, _policy: str) -> dict:
        return {
            "risk_score": 85,
            "risk_level": "high",
            "compliance_score": 0,
            "findings": [
                {
                    "title": "Unilateral Fee Increase",
                    "severity": "high",
                    "description": "Supplier may modify fees without mutual agreement.",
                    "evidence": "Fee modification clause lacks bilateral consent requirement.",
                    "recommendation": "Require bilateral written agreement before any fee modification.",
                    "risk_impact": 50,
                    "compliance_impact": 25,
                    "source_section": "Section 7.2 — Pricing & Fees",
                    "evidence_quote": "Supplier may modify applicable fees upon 30 days' notice to Customer without requiring mutual written agreement.",
                },
                {
                    "title": "Unlimited Liability",
                    "severity": "medium",
                    "description": "Liability cap is not clearly defined.",
                    "evidence": "No explicit liability limit.",
                    "recommendation": "Add specific liability caps.",
                    "risk_impact": 30,
                    "compliance_impact": 15,
                    "source_section": "Clause 12.3 — Limitation of Liability",
                    "evidence_quote": "Each party's total liability shall not exceed the greater of direct damages or fees paid in the preceding 12 months, provided that either party's liability for indemnification obligations shall be unlimited.",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["General"],
        }

    service = PassportService(analysis_engine, user_id="user", tenant_id="user")
    passport = await service.create_passport("contract", 1, "default", "text")
    evidence = await service.get_evidence(passport.passport_id)

    # Verify first finding source and quote are persisted in metadata
    assert evidence[0]["metadata"]["source_section"] == "Section 7.2 — Pricing & Fees"
    assert evidence[0]["metadata"]["evidence_quote"] == "Supplier may modify applicable fees upon 30 days' notice to Customer without requiring mutual written agreement."
    assert evidence[0]["contract_reference"] == "Section 7.2 — Pricing & Fees"

    # Verify second finding source and quote
    assert evidence[1]["metadata"]["source_section"] == "Clause 12.3 — Limitation of Liability"
    assert evidence[1]["metadata"]["evidence_quote"] == "Each party's total liability shall not exceed the greater of direct damages or fees paid in the preceding 12 months, provided that either party's liability for indemnification obligations shall be unlimited."
    assert evidence[1]["contract_reference"] == "Clause 12.3 — Limitation of Liability"

    # Verify recommendation is preserved
    assert evidence[0]["metadata"]["recommendation"] == "Require bilateral written agreement before any fee modification."
    assert evidence[1]["metadata"]["recommendation"] == "Add specific liability caps."