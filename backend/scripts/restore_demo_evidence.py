r"""
Restores the risk_impact field on an evidence_records document after the
tamper_demo.py script has modified it, so the item is clean for a real demo run.

Run from backend/ with the project venv:
    .\.venv\Scripts\python.exe scripts\restore_demo_evidence.py <evidence_id>
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
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: restore_demo_evidence.py <evidence_id> [risk_impact]")
    evidence_id = sys.argv[1]
    settings = get_settings()
    repo = FirestoreRepository("evidence_records", settings=settings)
    anchor_repo = EvidenceAnchorRepository("evidence_anchors", settings=settings)

    record = repo.get(evidence_id)
    if not record:
        raise SystemExit(f"No evidence_records document found for {evidence_id}")

    anchor = anchor_repo.get(evidence_id)
    if not anchor:
        raise SystemExit(f"No evidence anchor found for {evidence_id}")
    anchored_hash = str(anchor.get("evidence_hash", "")).removeprefix("0x").lower()
    verifier = get_ethereum_anchor_service(
        settings=settings,
        repository=anchor_repo,
        evidence_repository=repo,
    )
    verification = asyncio.run(verifier.verify_evidence(evidence_id))
    if verification.get("status") != "TAMPERED":
        raise SystemExit("Evidence is not currently tampered; refusing to restore.")

    restored_risk_impact = None
    for candidate in range(0, 101):
        candidate_record = {**record, "risk_impact": candidate}
        if hash_evidence_item(candidate_record).lower() == anchored_hash:
            restored_risk_impact = candidate
            break
    if restored_risk_impact is None:
        raise SystemExit(
            "Unable to determine the original risk_impact from the immutable anchor; "
            "refusing to write."
        )
    if len(sys.argv) == 3:
        try:
            supplied_value = float(sys.argv[2])
        except ValueError as error:
            raise SystemExit("Supplied risk_impact must be numeric.") from error
        if supplied_value != restored_risk_impact:
            raise SystemExit("Supplied risk_impact does not match the anchored value; refusing to write.")
    if hash_evidence_item({**record, "risk_impact": restored_risk_impact}).lower() != anchored_hash:
        raise SystemExit(
            "Restored evidence hash does not match its immutable anchor; refusing to write."
        )
    repo.set(evidence_id, {"risk_impact": restored_risk_impact}, merge=True)

    restored_verification = asyncio.run(verifier.verify_evidence(evidence_id))
    if restored_verification.get("status") != "VERIFIED":
        raise SystemExit("Restored evidence did not verify against its immutable anchor.")

    print("--- RESTORED ---")
    print("Evidence ID:", evidence_id)
    print("risk_impact:", restored_risk_impact)
    print("anchored hash:", anchored_hash)
    print("restored hash:", restored_verification["computed_hash"])
    print("VERIFIED")
    print("ON-CHAIN HASH MATCH")


if __name__ == "__main__":
    main()
