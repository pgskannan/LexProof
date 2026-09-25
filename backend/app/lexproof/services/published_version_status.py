"""Read-only status projection for published contract versions."""

from __future__ import annotations

from typing import Any

from ..domains.passport.utils.hashing import hash_evidence_item
from ..repositories.firestore import FirestoreRepository


STATUS_CONFIRMED = "confirmed"
STATUS_PROCESSING = "processing"
STATUS_FAILED = "failed"
STATUS_ACTION_REQUIRED = "action_required"


def _matches_scope(evidence: dict[str, Any], proposal: dict[str, Any], finding: dict[str, Any] | None) -> bool:
    evidence_id = proposal.get("evidence_id") or (finding or {}).get("evidence_id")
    if evidence_id:
        return evidence.get("evidence_id") == evidence_id or evidence.get("id") == evidence_id

    source_section = (finding or {}).get("source_section") or proposal.get("evidence")
    if source_section:
        return evidence.get("contract_reference") == source_section or evidence.get("source_id") == source_section

    finding_id = proposal.get("finding_id")
    return bool(finding_id and evidence.get("source_id") == finding_id)


def effective_analysis_status(
    version: dict[str, Any],
    proposal: dict[str, Any],
    *,
    proof_confirmed: bool,
) -> str | None:
    """Resolve the analysis status a published version should report.

    The proposal's ``analysis_status`` is written by the post-publish
    background task. If that run failed and the version was later
    re-analyzed through the Analyze Version retry path, only the version
    document is updated, so the proposal keeps a stale "failed". A version
    that reports "complete" -- or whose evidence is fully anchored and
    hash-matched on chain -- has finished analysis, whatever the proposal
    still says.
    """
    if proof_confirmed or version.get("analysis_status") == "complete":
        return "complete"
    return proposal.get("analysis_status") or version.get("analysis_status")


def project_published_version_status(
    version: dict[str, Any] | None,
    proposal: dict[str, Any] | None,
    *,
    passports: FirestoreRepository,
    evidence_records: FirestoreRepository,
    evidence_anchors: FirestoreRepository,
    findings: FirestoreRepository | None = None,
) -> dict[str, Any]:
    """Build a status projection without changing any persisted state."""
    version = version or {}
    proposal = proposal or {}
    version_id = version.get("id") or version.get("version_id")
    is_published = bool(proposal.get("published_version_id") == version_id)

    passport = None
    passport_id = version.get("passport_id")
    if passport_id:
        passport = passports.get(passport_id)
    if passport is None and version_id:
        passport = next((item for item in passports.stream() if item.get("version_id") == version_id), None)
    if passport is None and version.get("contract_id") is not None:
        passport = next(
            (
                item for item in passports.stream()
                if item.get("contract_id") == version.get("contract_id")
                and item.get("contract_version") == version.get("version_number")
            ),
            None,
        )
    passport_id = passport_id or (passport or {}).get("passport_id") or (passport or {}).get("id")

    evidence = [
        item for item in evidence_records.stream()
        if passport_id
        and item.get("passport_id") == passport_id
        and item.get("evidence_type") != "metadata"
    ]
    finding = findings.get(proposal.get("finding_id")) if findings and proposal.get("finding_id") else None
    scoped_evidence = [item for item in evidence if _matches_scope(item, proposal, finding)]
    expected_evidence = scoped_evidence or evidence

    anchor_by_id = {
        item.get("evidence_id") or item.get("id"): item
        for item in evidence_anchors.stream()
        if item.get("evidence_id") or item.get("id")
    }
    matched_count = 0
    for item in expected_evidence:
        evidence_id = item.get("evidence_id") or item.get("id")
        anchor = anchor_by_id.get(evidence_id)
        if not anchor:
            continue
        local_hash = hash_evidence_item(item).lower().removeprefix("0x")
        anchor_hash = str(anchor.get("evidence_hash") or "").lower().removeprefix("0x")
        if local_hash == anchor_hash:
            matched_count += 1

    evidence_count = len(expected_evidence)
    proof_confirmed = is_published and evidence_count > 0 and matched_count == evidence_count
    analysis_status = effective_analysis_status(version, proposal, proof_confirmed=proof_confirmed)
    if proof_confirmed:
        proof_status = STATUS_CONFIRMED
        recommended_action = "none"
    elif analysis_status in {"pending", "processing"}:
        proof_status = STATUS_PROCESSING
        recommended_action = "wait"
    elif analysis_status == "failed":
        proof_status = STATUS_FAILED
        recommended_action = "retry"
    else:
        proof_status = STATUS_ACTION_REQUIRED
        recommended_action = "retry"

    return {
        "publication_status": "published" if is_published else "unpublished",
        "analysis_status": analysis_status,
        "passport_status": (passport or {}).get("status"),
        "passport_id": passport_id,
        "evidence_count": evidence_count,
        "anchored_evidence_count": matched_count,
        "proof_status": proof_status,
        "recommended_action": recommended_action,
    }


def project_published_version_status_batch(
    versions: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
    passports: list[dict[str, Any]],
    evidence_records: list[dict[str, Any]],
    evidence_anchors: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Project many published versions from request-scoped collection snapshots."""
    versions_by_id = {item.get("id") or item.get("version_id"): item for item in versions}
    proposals_by_version = {
        item.get("published_version_id"): item
        for item in proposals
        if item.get("published_version_id")
    }
    passports_by_id = {
        item.get("passport_id") or item.get("id"): item
        for item in passports
        if item.get("passport_id") or item.get("id")
    }
    passports_by_version = {item.get("version_id"): item for item in passports if item.get("version_id")}
    passports_by_contract_version = {
        (item.get("contract_id"), item.get("contract_version")): item
        for item in passports
    }
    evidence_by_passport: dict[str, list[dict[str, Any]]] = {}
    for item in evidence_records:
        passport_id = item.get("passport_id")
        if passport_id and item.get("evidence_type") != "metadata":
            evidence_by_passport.setdefault(passport_id, []).append(item)
    anchors_by_evidence = {
        item.get("evidence_id") or item.get("id"): item
        for item in evidence_anchors
        if item.get("evidence_id") or item.get("id")
    }
    findings_by_id = {
        item.get("id") or item.get("finding_id"): item
        for item in (findings or [])
        if item.get("id") or item.get("finding_id")
    }
    result: dict[str, dict[str, Any]] = {}
    for version_id, version in versions_by_id.items():
        proposal = proposals_by_version.get(version_id)
        if not proposal:
            continue
        passport = passports_by_id.get(version.get("passport_id")) or passports_by_version.get(version_id)
        if passport is None:
            passport = passports_by_contract_version.get((version.get("contract_id"), version.get("version_number")))
        passport_id = version.get("passport_id") or (passport or {}).get("passport_id") or (passport or {}).get("id")
        evidence = evidence_by_passport.get(passport_id, []) if passport_id else []
        finding = findings_by_id.get(proposal.get("finding_id"))
        scoped_evidence = [item for item in evidence if _matches_scope(item, proposal, finding)]
        expected_evidence = scoped_evidence or evidence
        matched_count = sum(
            1
            for item in expected_evidence
            if (anchor := anchors_by_evidence.get(item.get("evidence_id") or item.get("id")))
            and hash_evidence_item(item).lower().removeprefix("0x")
            == str(anchor.get("evidence_hash") or "").lower().removeprefix("0x")
        )
        proof_confirmed = bool(proposal.get("published_version_id") == version_id and expected_evidence and matched_count == len(expected_evidence))
        analysis_status = effective_analysis_status(version, proposal, proof_confirmed=proof_confirmed)
        if proof_confirmed:
            proof_status, recommended_action = STATUS_CONFIRMED, "none"
        elif analysis_status in {"pending", "processing"}:
            proof_status, recommended_action = STATUS_PROCESSING, "wait"
        elif analysis_status == "failed":
            proof_status, recommended_action = STATUS_FAILED, "retry"
        else:
            proof_status, recommended_action = STATUS_ACTION_REQUIRED, "retry"
        result[version_id] = {
            "publication_status": "published",
            "analysis_status": analysis_status,
            "passport_status": (passport or {}).get("status"),
            "passport_id": passport_id,
            "evidence_count": len(expected_evidence),
            "anchored_evidence_count": matched_count,
            "proof_status": proof_status,
            "recommended_action": recommended_action,
        }
    return result
