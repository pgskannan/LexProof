"""Server-side passport integrity verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .utils.hashing import (
    compute_passport_hash,
    hash_ai_analysis,
    hash_document,
    hash_evidence_package,
    hash_policy_version,
)

PASS = "PASS"
FAIL = "FAIL"
UNVERIFIABLE = "UNVERIFIABLE"


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


def _snapshot(passport_data: Dict[str, Any]) -> Dict[str, Any]:
    metadata = passport_data.get("metadata") or {}
    snapshot = metadata.get("verification_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _component_status(claimed: bool, digest: Optional[str], stored: str) -> str:
    """Map a recompute attempt onto PASS / FAIL / UNVERIFIABLE.

    A digest means the component was actually hashed (snapshot or live fallback).
    Claimed-but-unusable inputs fail closed. Unclaimed inputs with no digest are
    UNVERIFIABLE, never PASS.
    """
    if digest is not None:
        return PASS if digest == stored else FAIL
    if claimed:
        return FAIL
    return UNVERIFIABLE


def _recompute_document_hash(passport_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    snapshot = _snapshot(passport_data)
    if "document_content" not in snapshot:
        return False, None
    document_content = snapshot["document_content"]
    if not isinstance(document_content, str):
        return True, None
    normalized = snapshot.get("normalized_document")
    if normalized is None:
        normalized = ""
    elif not isinstance(normalized, str):
        return True, None
    return True, hash_document(document_content, normalized)


def _recompute_policy_hash(passport_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    snapshot = _snapshot(passport_data)
    if "policy_content" not in snapshot:
        return False, None
    policy_content = snapshot["policy_content"]
    if not isinstance(policy_content, str):
        return True, None
    return True, hash_policy_version(
        policy_id=snapshot.get("policy_id", "default-policy"),
        policy_content=policy_content,
        version=passport_data.get("policy_version", snapshot.get("policy_version", "")),
    )


def _recompute_analysis_hash(passport_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    snapshot = _snapshot(passport_data)
    if "analysis_result" not in snapshot:
        return False, None
    analysis_result = snapshot["analysis_result"]
    if not isinstance(analysis_result, dict):
        return True, None
    return True, hash_ai_analysis(
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
) -> Tuple[bool, Optional[str]]:
    """Recompute the evidence-package hash for comparison against the stored one.

    Prefers the immutable evidence snapshot captured at publish time (like the
    document/policy/analysis checks), falling back to publish-time live evidence
    for older passports. Later appends (anchoring, countersignatures) are not
    treated as tampering.
    """
    snapshot = _snapshot(passport_data)
    if "evidence_items" in snapshot:
        snapshot_evidence = snapshot["evidence_items"]
        # A present list, including [], is the published package. Returning
        # None here used to fail-open verify_passport_integrity when an
        # attacker replaced evidence_items with []. A present non-list is a
        # claimed but unusable input and must fail closed.
        if not isinstance(snapshot_evidence, list):
            return True, None
        return True, hash_evidence_package(_normalize_evidence_items(snapshot_evidence))
    source_items = evidence_as_of_publish(evidence_items, passport_data.get("created_at"))
    if not source_items:
        return False, None
    return False, hash_evidence_package(_normalize_evidence_items(source_items))


def verify_passport_integrity(
    passport_data: Dict[str, Any],
    evidence_items: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Verify a persisted passport by recomputing canonical hashes from stored data.

    Never trusts client-supplied hashes and never modifies the passport record.

    Component statuses are PASS, FAIL, or UNVERIFIABLE. UNVERIFIABLE means the
    snapshot does not claim that component (legacy / repaired evidence-only
    records). It is not treated as PASS. Overall ``verified`` is True only when
    no component is FAIL and the stored passport root binds the stored hashes.
    """
    stored_document_hash = passport_data.get("document_hash", "")
    stored_policy_hash = passport_data.get("policy_hash", "")
    stored_analysis_hash = passport_data.get("analysis_hash", "")
    stored_evidence_hash = passport_data.get("evidence_hash", "")
    stored_passport_hash = (passport_data.get("metadata") or {}).get("passport_hash", "")

    normalized_evidence = _normalize_evidence_items(evidence_items)

    document_claimed, recomputed_document_hash = _recompute_document_hash(passport_data)
    policy_claimed, recomputed_policy_hash = _recompute_policy_hash(passport_data)
    analysis_claimed, recomputed_analysis_hash = _recompute_analysis_hash(passport_data)
    evidence_claimed, recomputed_evidence_hash = _recompute_evidence_hash(
        passport_data, normalized_evidence
    )

    document_status = _component_status(document_claimed, recomputed_document_hash, stored_document_hash)
    policy_status = _component_status(policy_claimed, recomputed_policy_hash, stored_policy_hash)
    analysis_status = _component_status(analysis_claimed, recomputed_analysis_hash, stored_analysis_hash)
    evidence_status = _component_status(evidence_claimed, recomputed_evidence_hash, stored_evidence_hash)

    recomputed_passport_hash = compute_passport_hash(
        stored_document_hash,
        stored_policy_hash,
        stored_analysis_hash,
        stored_evidence_hash,
    )
    passport_hash_status = PASS if recomputed_passport_hash == stored_passport_hash else FAIL

    document_verified = document_status == PASS
    policy_verified = policy_status == PASS
    analysis_verified = analysis_status == PASS
    evidence_verified = evidence_status == PASS
    passport_hash_verified = passport_hash_status == PASS

    verified = all(
        status != FAIL
        for status in (
            document_status,
            policy_status,
            analysis_status,
            evidence_status,
            passport_hash_status,
        )
    )

    return {
        "verified": verified,
        "document_verified": document_verified,
        "policy_verified": policy_verified,
        "analysis_verified": analysis_verified,
        "evidence_verified": evidence_verified,
        "passport_hash_verified": passport_hash_verified,
        "document_status": document_status,
        "policy_status": policy_status,
        "analysis_status": analysis_status,
        "evidence_status": evidence_status,
        "passport_hash_status": passport_hash_status,
        "stored_passport_hash": stored_passport_hash,
        "recomputed_passport_hash": recomputed_passport_hash,
    }
