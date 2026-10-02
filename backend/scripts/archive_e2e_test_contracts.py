"""Move automated-test (Playwright E2E) contracts out of the "LexProof Demo"
organization into a separate "E2E Test Archive" organization, so judges and
demo viewers only see the real demo contracts.

Nothing is deleted. Only the `org_id` field changes, on:
  contracts, legal_passports, redline_proposals, workflow_instances
for the selected contracts. The previous value is kept in
`archived_from_org_id`, so `--undo` puts everything back.

Hashes are unaffected: passport and evidence fingerprints never include
org_id, and evidence_records / evidence_anchors are not touched at all.

DRY RUN BY DEFAULT. Usage (from backend/):
    .\.venv\Scripts\python.exe scripts\archive_e2e_test_contracts.py            # dry run: prints the plan
    .\.venv\Scripts\python.exe scripts\archive_e2e_test_contracts.py --confirm  # moves them
    .\.venv\Scripts\python.exe scripts\archive_e2e_test_contracts.py --undo --confirm   # moves them back

Selection: contracts in the demo org whose name starts with one of
TEST_NAME_PREFIXES (the names the Playwright specs upload).
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.repositories.firestore import FirestoreRepository

DEMO_ORG_ID = "lexproof-demo"
ARCHIVE_ORG_ID = "lexproof-e2e-archive"
ARCHIVE_ORG_NAME = "E2E Test Archive"
TEST_NAME_PREFIXES = ("e2e-",)
RELATED_COLLECTIONS = ("legal_passports", "redline_proposals", "workflow_instances")


def is_test_contract(contract: dict) -> bool:
    name = str(contract.get("name") or "").strip().lower()
    return name.startswith(TEST_NAME_PREFIXES)


def main() -> None:
    confirm = "--confirm" in sys.argv
    undo = "--undo" in sys.argv
    settings = get_settings()
    contracts = FirestoreRepository("contracts", settings=settings)
    orgs = FirestoreRepository("organizations", settings=settings)

    if undo:
        source_org, target_org = ARCHIVE_ORG_ID, DEMO_ORG_ID
        selected = [c for c in contracts.query(equal={"org_id": ARCHIVE_ORG_ID}) if c.get("archived_from_org_id") == DEMO_ORG_ID]
    else:
        source_org, target_org = DEMO_ORG_ID, ARCHIVE_ORG_ID
        demo_contracts = [c for c in contracts.query(equal={"org_id": DEMO_ORG_ID}) if c.get("id")]
        selected = [c for c in demo_contracts if is_test_contract(c)]
        kept = sorted((c for c in demo_contracts if not is_test_contract(c)), key=lambda c: str(c.get("name") or ""))
        print(f"Demo org '{DEMO_ORG_ID}' has {len(demo_contracts)} contracts.")
        print(f"\nKEEP in the demo org ({len(kept)}):")
        for c in kept:
            print(f"   {c.get('name')}")

    selected.sort(key=lambda c: str(c.get("name") or ""))
    print(f"\nMOVE {source_org} -> {target_org} ({len(selected)}):")
    for c in selected:
        print(f"   {c.get('name')}  [{c['id']}]")

    unscoped = [c for c in contracts.stream() if not c.get("org_id")]
    if unscoped and not undo:
        print(f"\nNote: {len(unscoped)} contract(s) have no org_id at all (legacy). Not touched; listed for information:")
        for c in sorted(unscoped, key=lambda c: str(c.get("name") or ""))[:25]:
            print(f"   {c.get('name')}  [{c.get('id')}]")

    related_plan: dict[str, list[str]] = {}
    ids = [c["id"] for c in selected]
    for collection in RELATED_COLLECTIONS:
        repo = FirestoreRepository(collection, settings=settings)
        docs = repo.query_in("contract_id", ids) if ids else []
        related_plan[collection] = [d["id"] for d in docs if d.get("id") and d.get("org_id") == source_org]
        print(f"   related {collection}: {len(related_plan[collection])}")

    if not confirm:
        print("\nDRY RUN: nothing changed. Re-run with --confirm to apply.")
        return
    if not selected:
        print("\nNothing to move.")
        return

    now = datetime.now(timezone.utc).isoformat()
    if not undo and not orgs.get(ARCHIVE_ORG_ID):
        orgs.set(ARCHIVE_ORG_ID, {"org_id": ARCHIVE_ORG_ID, "name": ARCHIVE_ORG_NAME, "status": "active",
                                  "created_by": "archive_e2e_test_contracts", "created_at": now})
        print(f"Created organization '{ARCHIVE_ORG_NAME}' ({ARCHIVE_ORG_ID}).")

    def move_fields() -> dict:
        if undo:
            return {"org_id": DEMO_ORG_ID, "archived_from_org_id": None, "archived_at": None}
        return {"org_id": ARCHIVE_ORG_ID, "archived_from_org_id": DEMO_ORG_ID, "archived_at": now}

    for c in selected:
        contracts.set(c["id"], move_fields(), merge=True)
    for collection, doc_ids in related_plan.items():
        repo = FirestoreRepository(collection, settings=settings)
        for doc_id in doc_ids:
            repo.set(doc_id, move_fields(), merge=True)
    print(f"\nDone: moved {len(selected)} contract(s) and "
          f"{sum(len(v) for v in related_plan.values())} related record(s) to '{target_org}'.")


if __name__ == "__main__":
    main()
