"""
Restores the risk_impact field on an evidence_records document after the
tamper_demo.py script has modified it, so the item is clean for a real demo run.

Run from backend/ with the project venv:
    .\.venv\Scripts\python.exe scripts\restore_demo_evidence.py <evidence_id> <risk_impact>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.config import get_settings


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: restore_demo_evidence.py <evidence_id> <risk_impact>")
    evidence_id = sys.argv[1]
    risk_impact = int(sys.argv[2])

    settings = get_settings()
    repo = FirestoreRepository("evidence_records", settings=settings)

    record = repo.get(evidence_id)
    if not record:
        raise SystemExit(f"No evidence_records document found for {evidence_id}")

    print("--- BEFORE ---")
    print("risk_impact:", record.get("risk_impact"))

    record["risk_impact"] = risk_impact
    repo.set(evidence_id, record)

    print(f"--- RESTORED: risk_impact set back to {risk_impact} ---")


if __name__ == "__main__":
    main()
