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
from app.lexproof.config import get_settings


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: tamper_demo.py <evidence_id>")
    evidence_id = sys.argv[1]

    settings = get_settings()
    repo = FirestoreRepository("evidence_records", settings=settings)

    record = repo.get(evidence_id)
    if not record:
        raise SystemExit(f"No evidence_records document found for {evidence_id}")

    print("--- BEFORE (as anchored) ---")
    print("risk_impact:", record.get("risk_impact"))
    print("title:", record.get("title"))

    record["risk_impact"] = 5
    repo.set(evidence_id, record)

    print("--- TAMPERED: wrote risk_impact=5 directly to Firestore, bypassing the app API ---")
    print("Now click 'Check On-chain Verification' in the app to see the mismatch.")


if __name__ == "__main__":
    main()
