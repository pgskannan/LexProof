"""Deterministic SHA-256 hashing utilities for legal passports.

Provides deterministic hashing for document content, policy versions,
AI analysis results, and evidence packages to ensure immutability
and reproducibility of legal intelligence assessments.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


def compute_sha256_hash(data: Any) -> str:
    """Compute SHA-256 hash of data.

    Args:
        data: Data to hash (str, bytes, dict, or list)

    Returns:
        Hexadecimal SHA-256 hash (64 characters)

    Raises:
        ValueError: If data cannot be serialized to JSON
    """
    if isinstance(data, str):
        data_bytes = data.encode("utf-8")
    elif isinstance(data, bytes):
        data_bytes = data
    elif isinstance(data, (dict, list)):
        # Sort keys for deterministic hashing
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        data_bytes = data_str.encode("utf-8")
    else:
        data_str = str(data)
        data_bytes = data_str.encode("utf-8")

    return hashlib.sha256(data_bytes).hexdigest()


def hash_document(original_content: str, normalized_content: Optional[str] = None) -> str:
    """Compute hash for document content.

    Args:
        original_content: Original document content
        normalized_content: Optional normalized document content

    Returns:
        SHA-256 hash of document content

    Example:
        >>> hash_document("Contract text here", "contract text normalized")
        'a1b2c3d4...'
    """
    # Create a deterministic representation
    doc_data = {
        "original": original_content,
        "normalized": normalized_content or "",
        "hash_algorithm": "sha256",
    }

    return compute_sha256_hash(doc_data)


def hash_original_document(content: str) -> str:
    """Hash the original document bytes/text independently."""
    return compute_sha256_hash(content)


def hash_normalized_document(content: str) -> str:
    """Hash normalized document text independently."""
    return compute_sha256_hash(content)


def hash_policy_version(
    policy_id: str,
    policy_content: Optional[str] = None,
    version: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Compute hash for policy version.

    Args:
        policy_id: Policy identifier
        policy_content: Optional policy content
        version: Optional version string
        metadata: Optional policy metadata

    Returns:
        SHA-256 hash of policy version

    Example:
        >>> hash_policy_version("policy-1", version="1.0.0")
        'e5f6a7b8...'
    """
    policy_data = {
        "policy_id": policy_id,
        "version": version or "",
        "content": policy_content or "",
        "metadata": metadata or {},
    }

    return compute_sha256_hash(policy_data)


def hash_ai_analysis(
    analysis_result: Dict[str, Any],
    analysis_type: Optional[str] = None,
    model: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> str:
    """Compute hash for AI analysis result.

    Args:
        analysis_result: AI analysis result dictionary
        analysis_type: Optional analysis type (e.g., "risk", "compliance")
        model: Optional AI model identifier
        timestamp: Optional timestamp for reproducibility

    Returns:
        SHA-256 hash of AI analysis

    Example:
        >>> hash_ai_analysis({"risk_score": 75}, model="gemini-pro")
        'b7c8d9e0...'
    """
    # Ensure analysis_result is a dict
    if not isinstance(analysis_result, dict):
        analysis_result = {"result": analysis_result}

    analysis_data = {
        "analysis_type": analysis_type or "",
        "model": model or "",
        "timestamp": timestamp or "",
        "result": analysis_result,
    }

    return compute_sha256_hash(analysis_data)


EVIDENCE_HASH_FIELDS = (
    "evidence_id",
    "passport_id",
    "evidence_type",
    "title",
    "description",
    "content",
    "content_type",
    "risk_impact",
    "compliance_impact",
    "evidence_status",
    "contract_reference",
    "policy_reference",
    "analysis_reference",
    "source",
    "source_id",
    "metadata",
)


def canonicalize_evidence_item(evidence_item: Dict[str, Any]) -> Dict[str, Any]:
    """Return the canonical representation used for evidence hashing.

    Only fields in ``EVIDENCE_HASH_FIELDS`` define the evidence package. In
    particular, timestamps, the stored hash, and other operational bookkeeping
    are intentionally excluded so recomputation does not depend on persistence
    metadata.
    """
    return {
        field: evidence_item.get(field)
        for field in EVIDENCE_HASH_FIELDS
    }


def hash_evidence_package(evidence_items: list[Dict[str, Any]]) -> str:
    """Compute deterministic hash for the canonical evidence package.

    Args:
        evidence_items: List of evidence item dictionaries

    Returns:
        SHA-256 hash of evidence package

    Example:
        >>> hash_evidence_package([{"id": "e1", "type": "clause", "content": "..."}])
        'c8d9e0f1...'
    """
    canonical_items = [
        canonicalize_evidence_item(item)
        for item in evidence_items
    ]

    sorted_items = sorted(
        canonical_items,
        key=lambda x: x.get("evidence_id", ""),
    )

    evidence_data = {
        "evidence_count": len(sorted_items),
        "evidence_items": sorted_items,
    }

    return compute_sha256_hash(evidence_data)


def hash_evidence_item(evidence_item: Dict[str, Any]) -> str:
    """Compute hash for individual evidence item.

    This function implements the cryptographic evidence hash contract.
    The hash MUST include all fields that materially define the legal evidence.
    Modification of any of these fields should invalidate the hash.

    Cryptographically relevant fields (included in hash):
    - evidence_id: Unique evidence identifier
    - passport_id: Parent passport identifier (CRITICAL for linking evidence)
    - evidence_type: Type of evidence (CLAUSE, REDLINE, etc.)
    - title: Human-readable title
    - description: Detailed description
    - content: Evidence content (text, JSON, or base64)
    - content_type: MIME type of content
    - risk_impact: Risk impact score (CRITICAL for legal assessment)
    - compliance_impact: Compliance impact score (CRITICAL for legal assessment)
    - evidence_status: Validity status
    - contract_reference: Contract reference (clause, section)
    - policy_reference: Policy reference
    - analysis_reference: Reference to AI analysis finding
    - source: Source of evidence
    - source_id: Source identifier
    - metadata: Additional evidence metadata

    Operational metadata fields (excluded from hash):
    - created_at: Timestamp (can be recomputed)
    - verified_at: Timestamp (can be recomputed)
    - hash: Computed hash (can be recomputed)
    - Any other timestamps or bookkeeping fields

    Args:
        evidence_item: Evidence item dictionary

    Returns:
        SHA-256 hash of evidence item

    Example:
        >>> hash_evidence_item({"id": "e1", "title": "Clause", "content": "..."})
        'd9e0f1a2...'
    """
    # Use canonicalization to ensure all relevant fields are included
    # This guarantees passport_id, risk_impact, and compliance_impact are hashed
    item_data = canonicalize_evidence_item(evidence_item)

    return compute_sha256_hash(item_data)


def compute_passport_hash(
    document_hash: str,
    policy_hash: str,
    analysis_hash: str,
    evidence_hash: str,
) -> str:
    """Compute hash for complete passport snapshot.

    This is the final hash that represents the entire passport's immutability.

    Args:
        document_hash: Document hash
        policy_hash: Policy hash
        analysis_hash: AI analysis hash
        evidence_hash: Evidence package hash

    Returns:
        SHA-256 hash of passport components

    Example:
        >>> compute_passport_hash('a1b2', 'c3d4', 'e5f6', 'g7h8')
        'f1e2d3c4...'
    """
    passport_data = {
        "document_hash": document_hash,
        "policy_hash": policy_hash,
        "analysis_hash": analysis_hash,
        "evidence_hash": evidence_hash,
        "passport_hash_algorithm": "sha256",
    }

    return compute_sha256_hash(passport_data)


def compute_passport_key(passport_id: str) -> str:
    """Compute the on-chain identity key for a Legal Passport root anchor.

    This is deliberately Keccak-256 (Ethereum's hash function), NOT the SHA-256
    used everywhere else in this module -- it is a storage/identity key for the
    additive LexProofPassportRegistry contract, never a cryptographic commitment
    of passport content, and it is computed independently of, and does not
    change, ``compute_passport_hash`` (the SHA-256 v1 passport root).

    passportKey = keccak256(UTF-8(passport_id))

    The passport_id UUID itself is never sent as plaintext calldata; only this
    32-byte key and the 32-byte passport root are ever put on-chain.

    Args:
        passport_id: Passport identifier (UUID string)

    Returns:
        Lowercase 64-character hexadecimal string (no "0x" prefix), matching
        the format convention of the other hash functions in this module.
    """
    if not isinstance(passport_id, str) or not passport_id:
        raise ValueError("passport_id must be a non-empty string")

    # Imported locally (not at module scope) so this SHA-256 hashing module,
    # used throughout passport CREATE/VERIFY, does not gain a hard dependency
    # on web3 for callers that never touch blockchain anchoring.
    from web3 import Web3

    return Web3.keccak(text=passport_id).hex().removeprefix("0x").lower()


def passport_root_bytes32(passport_hash: str) -> bytes:
    """Decode the existing v1 hex `metadata.passport_hash` into the bytes32
    value submitted on-chain as `passportRoot`. Pure formatting -- does not
    recompute or alter the hash itself.
    """
    normalized = passport_hash.lower().removeprefix("0x")
    if len(normalized) != 64:
        raise ValueError("passport_hash must be a 64-character hexadecimal SHA-256 hash")
    return bytes.fromhex(normalized)


def verify_hash_consistency(
    computed_hash: str,
    original_hash: str,
) -> bool:
    """Verify hash consistency.

    Args:
        computed_hash: Hash computed from current data
        original_hash: Original hash to verify against

    Returns:
        True if hashes match, False otherwise
    """
    return computed_hash == original_hash


def generate_evidence_id() -> str:
    """Generate unique evidence identifier.

    Returns:
        UUID v4 string as evidence ID
    """
    import uuid

    return str(uuid.uuid4())


def generate_passport_id() -> str:
    """Generate unique passport identifier.

    Returns:
        UUID v4 string as passport ID
    """
    import uuid

    return str(uuid.uuid4())
