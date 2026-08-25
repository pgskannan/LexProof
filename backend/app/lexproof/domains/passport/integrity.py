"""Server-side passport integrity verification."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .utils.hashing import (
    compute_passport_hash,
    hash_ai_analysis,
    hash_document,
    hash_evidence_package,
    hash_policy_version,
)


def _normalize_evidence_items(evidence_items: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    if not evidence_items:
        return []

    normalized: List[Dict[str, Any]] = []
    for item in evidence_items:
        if isinstance(item, dict):
            normalized.append(item)
        elif hasattr(item, "model_dump"):
            normalized.append(item.model_dump(mode="json"))
        elif hasattr(item, "dict"):
            normalized.append(item.dict())
        else:
            normalized.append(dict(item))
    return normalized


def _recompute_document_hash(passport_data: Dict[str, Any]) -> Optional[str]:
    metadata = passport_data.get("metadata") or {}
    snapshot = metadata.get("verification_snapshot") or {}
    document_content = snapshot.get("document_content")
    if document_content is None:
        return None
    return hash_document(
        document_content,
        snapshot.get("normalized_document", ""),
    )


def _recompute_policy_hash(passport_data: Dict[str, Any]) -> Optional[str]:
    metadata = passport_data.get("metadata") or {}
    snapshot = metadata.get("verification_snapshot") or {}
    if "policy_content" not in snapshot:
        return None
    return hash_policy_version(
        policy_id=snapshot.get("policy_id", "default-policy"),
        policy_content=snapshot.get("policy_content", ""),
        version=passport_data.get("policy_version", snapshot.get("policy_version", "")),
    )


def _recompute_analysis_hash(passport_data: Dict[str, Any]) -> Optional[str]:
    metadata = passport_data.get("metadata") or {}
    snapshot = metadata.get("verification_snapshot") or {}
    analysis_result = snapshot.get("analysis_result")
    if not isinstance(analysis_result, dict):
        return None
    return hash_ai_analysis(
        analysis_result=analysis_result,
        analysis_type=snapshot.get("analysis_type", "risk_and_compliance"),
    )


def _recompute_evidence_hash(evidence_items: List[Dict[str, Any]]) -> Optional[str]:
    if not evidence_items:
        return None
    return hash_evidence_package(evidence_items)


def verify_passport_integrity(
    passport_data: Dict[str, Any],
    evidence_items: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Verify a persisted passport by recomputing canonical hashes from stored data.

    Never trusts client-supplied hashes and never modifies the passport record.
    """
    stored_document_hash = passport_data.get("document_hash", "")
    stored_policy_hash = passport_data.get("policy_hash", "")
    stored_analysis_hash = passport_data.get("analysis_hash", "")
    stored_evidence_hash = passport_data.get("evidence_hash", "")
    stored_passport_hash = (passport_data.get("metadata") or {}).get("passport_hash", "")

    normalized_evidence = _normalize_evidence_items(evidence_items)

    recomputed_document_hash = _recompute_document_hash(passport_data)
    recomputed_policy_hash = _recompute_policy_hash(passport_data)
    recomputed_analysis_hash = _recompute_analysis_hash(passport_data)
    recomputed_evidence_hash = _recompute_evidence_hash(normalized_evidence)

    document_verified = (
        recomputed_document_hash == stored_document_hash
        if recomputed_document_hash is not None
        else True
    )
    policy_verified = (
        recomputed_policy_hash == stored_policy_hash
        if recomputed_policy_hash is not None
        else True
    )
    analysis_verified = (
        recomputed_analysis_hash == stored_analysis_hash
        if recomputed_analysis_hash is not None
        else True
    )
    evidence_verified = (
        recomputed_evidence_hash == stored_evidence_hash
        if recomputed_evidence_hash is not None
        else True
    )

    recomputed_passport_hash = compute_passport_hash(
        stored_document_hash,
        stored_policy_hash,
        stored_analysis_hash,
        stored_evidence_hash,
    )
    passport_hash_verified = recomputed_passport_hash == stored_passport_hash

    verified = all(
        [
            document_verified,
            policy_verified,
            analysis_verified,
            evidence_verified,
            passport_hash_verified,
        ]
    )

    return {
        "verified": verified,
        "document_verified": document_verified,
        "policy_verified": policy_verified,
        "analysis_verified": analysis_verified,
        "evidence_verified": evidence_verified,
        "passport_hash_verified": passport_hash_verified,
        "stored_passport_hash": stored_passport_hash,
        "recomputed_passport_hash": recomputed_passport_hash,
    }
