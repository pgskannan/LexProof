"""Utilities for Legal Passport domain."""

from .hashing import (
    compute_sha256_hash,
    hash_document,
    hash_original_document,
    hash_normalized_document,
    hash_policy_version,
    hash_ai_analysis,
    hash_evidence_package,
    hash_evidence_item,
    compute_passport_hash,
    verify_hash_consistency,
    generate_evidence_id,
    generate_passport_id,
)

__all__ = [
    "compute_sha256_hash",
    "hash_document",
    "hash_policy_version",
    "hash_ai_analysis",
    "hash_evidence_package",
    "hash_evidence_item",
    "compute_passport_hash",
    "verify_hash_consistency",
    "generate_evidence_id",
    "generate_passport_id",
]
