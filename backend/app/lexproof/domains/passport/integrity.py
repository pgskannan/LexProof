"""Server-side passport integrity verification."""

from __future__ import annotations

from datetime import datetime, timezone
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


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _item_created_at(item: Any) -> Any:
    if isinstance(item, dict):
        return item.get("created_at")
    return getattr(item, "created_at", None)


def evidence_as_of_publish(evidence_items: Iterable[Any], published_at: Any) -> List[Any]:
    """Return evidence that existed at publish time, excluding later appends.

    Post-publish items (anchoring bookkeeping, counterparty countersignatures)
    must not make a legitimate passport look tampered.
    """
    items = list(evidence_items or [])
    cutoff = _parse_timestamp(published_at)
    if cutoff is None:
        return [
            item
            for item in items
            if str(
                (item.get("evidence_type") if isinstance(item, dict) else getattr(item, "evidence_type", ""))
                or ""
            )
            != "counterparty_countersignature"
        ]
    matched: List[Any] = []
    for item in items:
        created = _parse_timestamp(_item_created_at(item))
        evidence_type = item.get("evidence_type") if isinstance(item, dict) else getattr(item, "evidence_type", "")
        if str(evidence_type or "") == "counterparty_countersignature":
            continue
        if created is None or created <= cutoff:
            matched.append(item)
    return matched


def _recompute_evidence_hash(
    passport_data: Dict[str, Any], evidence_items: List[Dict[str, Any]]
) -> Optional[str]:
    """Recompute the evidence-package hash for comparison against the stored one.

    Prefers the immutable evidence snapshot captured at publish time (like the
    document/policy/analysis checks), falling back to publish-time live evidence
    for older passports. Later appends (anchoring, countersignatures) are not
    treated as tampering.
    """
    metadata = passport_data.get("metadata") or {}
    snapshot = metadata.get("verification_snapshot") or {}
    snapshot_evidence = snapshot.get("evidence_items")
    if snapshot_evidence is not None:
        source_items = snapshot_evidence
    else:
        source_items = evidence_as_of_publish(evidence_items, passport_data.get("created_at"))
    if not source_items:
        return None
    return hash_evidence_package(_normalize_evidence_items(source_items))


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
    recomputed_evidence_hash = _recompute_evidence_hash(passport_data, normalized_evidence)

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
