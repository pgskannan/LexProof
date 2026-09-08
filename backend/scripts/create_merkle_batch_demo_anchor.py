"""
DEMO ONLY: creates one dedicated, isolated evidence fixture and anchors it with a
hand-crafted MOCK "MERKLE_BATCH" anchor record, to illustrate the proposed Hybrid
Anchoring architecture (batching several evidence hashes under one on-chain Merkle
root instead of one transaction per evidence item) described in
hackathon-polish-roadmap.md, initiative #1.

This is a demonstration of a proposed FUTURE anchoring strategy, not a real
anchoring path. It never touches the real, hard-won single-hash Ethereum
anchoring flow in ethereum_anchor_service.py / blockchain.py, and it never
submits a real Ethereum transaction. The record it writes is explicitly marked
"is_mock": true and uses an obviously non-functional transaction_hash so it can
never be confused with (or accidentally verified against) a real on-chain anchor.
The Merkle root/proof are computed for real (SHA-256, standard binary tree) over
one real evidence hash plus three synthetic sibling hashes, so the batch math
itself is genuine and demonstrable - only the "submitted to Ethereum" part is
simulated.

Run from backend/ with the project venv:
    .\.venv\Scripts\python.exe scripts\create_merkle_batch_demo_anchor.py

Idempotent-ish: re-running creates a brand new evidence_id each time (uses
uuid4), so it's always safe to run again, but you generally only need to run
this once and keep the resulting evidence_id for the demo.
"""
import hashlib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.domains.passport.utils.hashing import hash_evidence_item
from app.lexproof.repositories.firestore import (
    EvidenceAnchorRepository,
    FirestoreRepository,
)

# Same reference fixture create_tamper_demo_fixture.py uses, purely to borrow a
# valid passport_id / contract_id / owner_id to attach this demo evidence item to.
REFERENCE_EVIDENCE_ID = "72777ba7-d5bf-48e3-81f7-42a946bca284"


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _merkle_root_and_proof(leaf_hashes: list[str], leaf_index: int) -> tuple[str, list[dict]]:
    """Standard binary Merkle tree over hex leaf hashes. Returns (root, proof).

    proof is a list of {"position": "left"|"right", "hash": <hex>} describing the
    sibling hashes needed to recompute the root starting from leaf_hashes[leaf_index].
    An odd node at any level is paired with itself, matching the common convention.
    """
    level = list(leaf_hashes)
    index = leaf_index
    proof: list[dict] = []
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            if i == index or i + 1 == index:
                sibling_is_right = (index == i)
                sibling_hash = right if sibling_is_right else left
                proof.append({"position": "right" if sibling_is_right else "left", "hash": sibling_hash})
                index = len(next_level)
            next_level.append(_sha256_hex(left + right))
        level = next_level
    return level[0], proof


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("This one-shot script takes no arguments")

    settings = get_settings()
    records = FirestoreRepository("evidence_records", settings=settings)
    anchors = EvidenceAnchorRepository("evidence_anchors", settings=settings)

    source = records.get(REFERENCE_EVIDENCE_ID)
    if not source:
        raise SystemExit(
            f"Reference evidence record {REFERENCE_EVIDENCE_ID} not found; "
            "update REFERENCE_EVIDENCE_ID to any existing evidence_id in this environment."
        )

    evidence_id = str(uuid.uuid4())
    record = {
        "evidence_id": evidence_id,
        "passport_id": source["passport_id"],
        "contract_id": source["contract_id"],
        "contract_version": source["contract_version"],
        "owner_id": source["owner_id"],
        "evidence_type": "clause",
        "title": "Hybrid Anchoring Demo: Batched Evidence Item",
        "description": (
            "Dedicated fixture demonstrating the proposed Hybrid Anchoring architecture: "
            "several evidence hashes committed under one on-chain Merkle root instead of "
            "one Ethereum transaction per evidence item, to cut per-item anchoring cost."
        ),
        "content": "This evidence item is anchored via a simulated Merkle-batch commitment, not a direct single-hash transaction.",
        "content_type": "text/plain",
        "risk_impact": 0,
        "compliance_impact": 0,
        "evidence_status": "valid",
        "contract_reference": source.get("contract_reference", "Demo"),
        "policy_reference": "",
        "analysis_reference": "hybrid_anchoring_demo",
        "source": "create_merkle_batch_demo_anchor",
        "source_id": "hybrid_anchoring_demo",
        "metadata": {"purpose": "hybrid_anchoring_demo", "fixture": "merkle_batch"},
    }
    if records.get(evidence_id) or anchors.get(evidence_id):
        raise SystemExit(f"Generated fixture ID unexpectedly already exists: {evidence_id}")

    evidence_hash = hash_evidence_item(record).lower()

    # Three synthetic sibling leaves standing in for other evidence items that
    # would, in a real Hybrid Anchoring build, be batched together in the same
    # on-chain commitment. These are illustrative only - not real evidence hashes.
    synthetic_siblings = [
        _sha256_hex(f"hybrid-anchoring-demo-sibling-{evidence_id}-1"),
        _sha256_hex(f"hybrid-anchoring-demo-sibling-{evidence_id}-2"),
        _sha256_hex(f"hybrid-anchoring-demo-sibling-{evidence_id}-3"),
    ]
    leaves = [evidence_hash] + synthetic_siblings
    merkle_root, merkle_proof = _merkle_root_and_proof(leaves, leaf_index=0)

    records.set(evidence_id, record)

    blockchain_proof = {
        "evidence_id": evidence_id,
        "passport_id": record["passport_id"],
        "evidence_hash": evidence_hash,
        "anchoring_method": "MERKLE_BATCH",
        "is_mock": True,
        "blockchain_network": "ethereum-sepolia",
        "batch_id": f"demo-batch-{evidence_id[:8]}",
        "batch_size": len(leaves),
        "merkle_root": merkle_root,
        "merkle_proof": merkle_proof,
        # Deliberately not a valid 0x-prefixed transaction hash: this batch was
        # never submitted to Ethereum. Anything that renders this value should
        # display it as-is (or hide the "View on Etherscan" action) rather than
        # link out, since there is nothing real to link to.
        "transaction_hash": "SIMULATED-NOT-SUBMITTED-TO-ETHEREUM",
        "block_number": None,
        "anchored_at": datetime.now(timezone.utc).isoformat(),
        "anchored_by": "hybrid_anchoring_demo_script",
        "demo_note": (
            "This anchor is simulated to illustrate the proposed Hybrid Anchoring "
            "architecture (batched Merkle-root commitments). It was never submitted "
            "to Ethereum and is not part of the real, live-verified anchoring path."
        ),
    }
    anchors.set(evidence_id, blockchain_proof)

    print("--- HYBRID ANCHORING DEMO RECORD CREATED (SIMULATED, NOT ON-CHAIN) ---")
    print("Evidence ID:", evidence_id)
    print("Passport ID:", record["passport_id"])
    print("Evidence hash:", evidence_hash)
    print("Anchoring method:", blockchain_proof["anchoring_method"])
    print("Batch ID:", blockchain_proof["batch_id"])
    print("Batch size:", blockchain_proof["batch_size"])
    print("Merkle root:", merkle_root)
    print("Merkle proof:", merkle_proof)
    print()
    print("View it in the app: GET /api/evidence/" + evidence_id + "/anchor")
    print("Or open the contract's Legal Passport / lifecycle page for passport", record["passport_id"])


if __name__ == "__main__":
    main()
