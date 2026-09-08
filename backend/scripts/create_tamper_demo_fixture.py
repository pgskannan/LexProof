"""Create and anchor one clean, dedicated tamper-demo evidence fixture."""

import asyncio
import sys
import uuid
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
from app.lexproof.services.ethereum_anchor_service import EthereumAnchorService


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("This one-shot script takes no arguments")

    settings = get_settings()
    records = FirestoreRepository("evidence_records", settings=settings)
    anchors = EvidenceAnchorRepository("evidence_anchors", settings=settings)
    source = records.get("72777ba7-d5bf-48e3-81f7-42a946bca284")
    if not source:
        raise SystemExit("The existing demo record is required as a reference")

    evidence_id = str(uuid.uuid4())
    record = {
        "evidence_id": evidence_id,
        "passport_id": source["passport_id"],
        "contract_id": source["contract_id"],
        "contract_version": source["contract_version"],
        "owner_id": source["owner_id"],
        "evidence_type": "clause",
        "title": "Tamper Demonstration: Clean Liability Assessment",
        "description": "Dedicated fixture for demonstrating anchored evidence tamper detection.",
        "content": "The liability cap applies to sensitive health data.",
        "content_type": "text/plain",
        "risk_impact": 90,
        "compliance_impact": 70,
        "evidence_status": "valid",
        "contract_reference": source.get("contract_reference", "Section 9"),
        "policy_reference": "",
        "analysis_reference": "tamper_demo_fixture",
        "source": "tamper_demo",
        "source_id": "tamper_demo_clean_fixture",
        "metadata": {"purpose": "tamper_demo", "fixture": "clean"},
    }
    if records.get(evidence_id) or anchors.get(evidence_id):
        raise SystemExit(f"Generated fixture ID unexpectedly already exists: {evidence_id}")

    original_hash = hash_evidence_item(record)
    records.set(evidence_id, record)
    service = EthereumAnchorService(
        settings=settings,
        repository=anchors,
        evidence_repository=records,
    )
    proof = asyncio.run(service.anchor_evidence(evidence_id))

    print("Evidence ID:", evidence_id)
    print("risk_impact:", record["risk_impact"])
    print("canonical hash:", original_hash)
    print("transaction hash:", proof["transaction_hash"])
    print("block number:", proof["block_number"])
    print("registry contract:", proof["contract_address"])
    print("network:", proof["blockchain_network"])
    print("verification baseline: run GET /api/verify/" + evidence_id)


if __name__ == "__main__":
    main()