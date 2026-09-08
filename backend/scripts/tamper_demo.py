r"""
DEMO ONLY: simulates an attacker/insider bypassing the LexProof application
and editing the evidence record directly in Firestore, to prove that
Ethereum-anchored evidence detects tampering even when the app's own
immutability guard (EvidenceRecordRepository) is bypassed entirely.

Run from backend/ with the project venv:
    .\.venv\Scripts\python.exe scripts\tamper_demo.py <evidence_id>

Writes directly via the base FirestoreRepository (no immutability check),
unlike the app's normal write path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.repositories.firestore import EvidenceAnchorRepository
from app.lexproof.config import get_settings
from app.lexproof.domains.passport.utils.hashing import hash_evidence_item
import asyncio

from app.lexproof.services.ethereum_anchor_service import get_ethereum_anchor_service


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: tamper_demo.py <evidence_id>")
    evidence_id = sys.argv[1]
    preferred_tampered_risk_impact = 5

    settings = get_settings()
    repo = FirestoreRepository("evidence_records", settings=settings)
    anchor_repo = EvidenceAnchorRepository("evidence_anchors", settings=settings)

    record = repo.get(evidence_id)
    if not record:
        raise SystemExit(f"No evidence_records document found for {evidence_id}")

    verifier = get_ethereum_anchor_service(
        settings=settings,
        repository=anchor_repo,
        evidence_repository=repo,
    )
    verification = asyncio.run(verifier.verify_evidence(evidence_id))
    if verification.get("status") != "VERIFIED":
        if verification.get("status") == "TAMPERED":
            print("ALREADY TAMPERED")
            print("Evidence ID:", evidence_id)
            print("Current risk_impact:", record.get("risk_impact"))
            return
        raise SystemExit(
            "Evidence is not verified against its Ethereum anchor; refusing to modify it."
        )

    current_risk_impact = record.get("risk_impact")
    anchored_hash = str(verification["evidence_hash_on_chain"]).removeprefix("0x").lower()
    current_hash = verification["computed_hash"].lower()
    if current_hash != anchored_hash:
        raise SystemExit(
            "Evidence is already modified or does not match its Ethereum anchor."
        )

    tampered_risk_impact = preferred_tampered_risk_impact
    if tampered_risk_impact == current_risk_impact:
        tampered_risk_impact = 4
    candidate_record = {**record, "risk_impact": tampered_risk_impact}
    tampered_hash = hash_evidence_item(candidate_record).lower()
    if tampered_hash == anchored_hash:
        tampered_risk_impact = 6 if current_risk_impact != 6 else 4
        candidate_record["risk_impact"] = tampered_risk_impact
        tampered_hash = hash_evidence_item(candidate_record).lower()
    if tampered_hash == anchored_hash:
        raise SystemExit("Unable to produce a tampered risk_impact; refusing to write.")

    repo.set(evidence_id, {"risk_impact": tampered_risk_impact}, merge=True)

    print("--- TAMPERED ---")
    print("Evidence ID:", evidence_id)
    print(f"original risk_impact: {current_risk_impact}")
    print("tampered risk_impact:", tampered_risk_impact)
    print("anchored hash:", anchored_hash)
    print("recomputed hash after tampering:", tampered_hash)
    print("hashes match:", tampered_hash == anchored_hash)
    print("The Ethereum anchor was NOT modified.")


if __name__ == "__main__":
    main()
