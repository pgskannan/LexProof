"""Assemble a portable, independently-verifiable passport proof package."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HOW_TO_VERIFY = (
    "Open verify-offline.html in any browser — LexProof's servers do not need to be running. "
    "Load this JSON bundle and optionally the original contract file. "
    "The page recomputes SHA-256 hashes in your browser and reads the LexProofRegistry "
    "contract on Ethereum Sepolia through a public RPC endpoint, not through LexProof. "
    "VERIFIED means the on-chain hash matches this bundle. MISMATCH means the bundle, "
    "the document, or the on-chain record has been altered. Reaching Sepolia still "
    "requires a network connection to a public RPC; it does not require LexProof to be online."
)

DEFAULT_SEPOLIA_RPC = "https://ethereum-sepolia-rpc.publicnode.com"
DEFAULT_REGISTRY = "0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191"


def _anchor_payload(anchor: dict[str, Any] | None) -> dict[str, Any] | None:
    if not anchor:
        return None
    if not (anchor.get("transaction_hash") or anchor.get("evidence_hash") or anchor.get("contract_address")):
        return None
    return {
        "blockchain_network": anchor.get("blockchain_network"),
        "contract_address": anchor.get("contract_address"),
        "transaction_hash": anchor.get("transaction_hash"),
        "block_number": anchor.get("block_number"),
        "anchored_at": anchor.get("anchored_at"),
        "evidence_hash": anchor.get("evidence_hash"),
        "anchored_by": anchor.get("anchored_by"),
    }


def build_proof_package(
    passport_doc: dict[str, Any],
    *,
    evidence_items: list[dict[str, Any]] | None = None,
    anchors_by_id: dict[str, dict[str, Any]] | None = None,
    contract_name: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    metadata = passport_doc.get("metadata") or {}
    snapshot = metadata.get("verification_snapshot") or {}
    snapshot_evidence = list(snapshot.get("evidence_items") or [])
    live_evidence = list(evidence_items or [])
    items = snapshot_evidence or live_evidence
    anchors = anchors_by_id or {}

    evidence_payload = []
    registry_address = DEFAULT_REGISTRY
    for item in items:
        evidence_id = str(item.get("evidence_id") or item.get("id") or "")
        anchor = _anchor_payload(anchors.get(evidence_id))
        if anchor and anchor.get("contract_address"):
            registry_address = str(anchor["contract_address"])
        evidence_payload.append(
            {
                "evidence_id": evidence_id,
                "title": item.get("title"),
                "hash": item.get("hash"),
                "hash_algorithm": "sha256",
                "anchor": anchor,
            }
        )

    return {
        "bundle_version": 1,
        "bundle_generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "hash_algorithm": "sha256",
        "how_to_verify": HOW_TO_VERIFY,
        "sepolia_rpc_url": DEFAULT_SEPOLIA_RPC,
        "registry_contract_address": registry_address,
        "contract": {
            "contract_id": passport_doc.get("contract_id"),
            "name": contract_name
            or (metadata.get("contract_name") or metadata.get("contract_title"))
            or passport_doc.get("contract_id"),
            "contract_version": passport_doc.get("contract_version"),
            "passport_id": passport_doc.get("passport_id") or passport_doc.get("id"),
        },
        "hashes": {
            "document_hash": passport_doc.get("document_hash"),
            "policy_hash": passport_doc.get("policy_hash"),
            "analysis_hash": passport_doc.get("analysis_hash"),
            "evidence_hash": passport_doc.get("evidence_hash"),
            "passport_hash": metadata.get("passport_hash"),
            "original_document_hash": metadata.get("original_document_hash"),
            "normalized_document_hash": metadata.get("normalized_document_hash"),
        },
        "verification_snapshot": snapshot or None,
        "evidence": evidence_payload,
    }
