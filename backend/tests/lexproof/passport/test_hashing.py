"""Unit tests for deterministic passport hashes."""

from app.lexproof.domains.passport.utils.hashing import (
    compute_sha256_hash,
    hash_ai_analysis,
    hash_evidence_package,
    hash_normalized_document,
    hash_original_document,
)


def test_hashes_are_deterministic():
    analysis = {"risk_score": 12, "findings": [{"id": "f-1"}]}
    evidence = [{"evidence_id": "e-2", "content": "b"}, {"evidence_id": "e-1", "content": "a"}]

    assert compute_sha256_hash({"b": 2, "a": 1}) == compute_sha256_hash({"a": 1, "b": 2})
    assert hash_ai_analysis(analysis) == hash_ai_analysis(analysis)
    assert hash_evidence_package(evidence) == hash_evidence_package(list(reversed(evidence)))
    assert hash_original_document("contract") != hash_normalized_document("contract ")
    assert len(hash_original_document("contract")) == 64
