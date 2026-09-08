"""Delete accumulated test contracts and their related records, EXCEPT the
protected demo fixtures.

This is a destructive, irreversible script (it hard-deletes Firestore
documents) and is DRY-RUN BY DEFAULT. It only writes anything if you pass
--confirm on the command line. Always run it once without --confirm first,
read the printed plan carefully, and only re-run with --confirm once you're
sure.

Usage (from the backend/ directory):
    .\.venv\Scripts\python.exe scripts\cleanup_test_contracts.py            # dry run, prints the plan
    .\.venv\Scripts\python.exe scripts\cleanup_test_contracts.py --confirm  # actually deletes

Safety behavior:
  - PROTECTED_CONTRACT_IDS are never touched, no matter what.
  - Any other contract that has at least one ANCHORED evidence item is
    SKIPPED by default (anchored evidence is deliberately immutable/
    undeletable via the app's own EvidenceRecordRepository lock -- this
    script respects that same lock rather than working around it). Pass
    --include-anchored to also delete those (their evidence_records/
    evidence_anchors will simply be left in place if they can't be removed;
    the script reports this rather than failing).
  - Everything else (uploaded but never meaningfully anchored test
    contracts) is deleted across: contracts, contract_versions,
    legal_passports, risk_findings, evidence_records, evidence_anchors,
    redline_proposals.
  - redline_reviews, redline_publication_audits, and blockchain_proofs are
    NOT touched by this script -- their exact linkage back to a contract_id
    wasn't verified, and any orphaned rows there are small, harmless
    metadata not shown in the main contracts list. Clean those up in a
    later pass if you want to.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.repositories.firestore import (
    EvidenceAnchorRepository,
    FirestoreRepository,
)

# Never touch these, under any circumstances.
PROTECTED_CONTRACT_IDS = {
    "797b61c9-4d50-41f6-b095-078561545fbd": "primary demo contract (V1->V2, published redline, 6/6 evidence anchored)",
    "50712c6d-cd84-408e-aac0-9c28ed09f2fe": "fixture contract referenced by create_tamper_demo_fixture.py and create_merkle_batch_demo_anchor.py (REFERENCE_EVIDENCE_ID)",
}


def main() -> None:
    confirm = "--confirm" in sys.argv
    include_anchored = "--include-anchored" in sys.argv

    settings = get_settings()
    contracts = FirestoreRepository("contracts", settings=settings)
    versions = FirestoreRepository("contract_versions", settings=settings)
    passports = FirestoreRepository("legal_passports", settings=settings)
    findings = FirestoreRepository("risk_findings", settings=settings)
    evidence_records = FirestoreRepository("evidence_records", settings=settings)
    evidence_anchors = EvidenceAnchorRepository("evidence_anchors", settings=settings)
    redline_proposals = FirestoreRepository("redline_proposals", settings=settings)

    all_contracts = {c["id"]: c for c in contracts.stream() if c.get("id")}
    print(f"Found {len(all_contracts)} contract documents.")

    all_evidence = list(evidence_records.stream())
    evidence_by_contract: dict[str, list[dict]] = {}
    for ev in all_evidence:
        cid = ev.get("contract_id")
        if cid:
            evidence_by_contract.setdefault(cid, []).append(ev)

    to_delete: list[str] = []
    skipped_anchored: list[str] = []
    protected_seen: list[str] = []

    for contract_id, contract in all_contracts.items():
        if contract_id in PROTECTED_CONTRACT_IDS:
            protected_seen.append(contract_id)
            continue

        contract_evidence = evidence_by_contract.get(contract_id, [])
        anchored_ids = [
            ev["evidence_id"] for ev in contract_evidence
            if ev.get("evidence_id") and evidence_anchors.get(ev["evidence_id"])
        ]

        if anchored_ids and not include_anchored:
            skipped_anchored.append(contract_id)
            continue

        to_delete.append(contract_id)

    print(f"\nProtected (never touched): {len(protected_seen)}")
    for cid in protected_seen:
        print(f"  KEEP  {cid}  -- {PROTECTED_CONTRACT_IDS[cid]}")

    print(f"\nSkipped (has anchored evidence, re-run with --include-anchored to also delete these): {len(skipped_anchored)}")
    for cid in skipped_anchored:
        name = all_contracts[cid].get("name", "?")
        print(f"  SKIP  {cid}  -- {name}")

    print(f"\nWill delete: {len(to_delete)} contract(s) and their related records")
    for cid in to_delete:
        name = all_contracts[cid].get("name", "?")
        print(f"  {'DELETE' if confirm else 'WOULD DELETE'}  {cid}  -- {name}")

    if not confirm:
        print("\nDRY RUN ONLY -- nothing was deleted. Re-run with --confirm to actually delete the contracts listed above.")
        return

    print("\n--confirm passed. Deleting now...")
    counts = {"contracts": 0, "contract_versions": 0, "legal_passports": 0, "risk_findings": 0, "evidence_records": 0, "evidence_anchors": 0, "redline_proposals": 0}
    left_locked: list[str] = []

    all_versions = list(versions.stream())
    all_passports = list(passports.stream())
    all_findings = list(findings.stream())
    all_proposals = list(redline_proposals.stream())

    for contract_id in to_delete:
        for ev in evidence_by_contract.get(contract_id, []):
            ev_id = ev.get("evidence_id")
            if not ev_id:
                continue
            if evidence_anchors.get(ev_id):
                try:
                    evidence_anchors.delete(ev_id)
                    counts["evidence_anchors"] += 1
                except Exception as exc:
                    print(f"  could not delete evidence_anchors/{ev_id}: {exc}")
            try:
                evidence_records.delete(ev_id)
                counts["evidence_records"] += 1
            except ValueError:
                left_locked.append(ev_id)
            except Exception as exc:
                print(f"  could not delete evidence_records/{ev_id}: {exc}")

        for v in all_versions:
            if v.get("contract_id") == contract_id and v.get("id"):
                versions.delete(v["id"])
                counts["contract_versions"] += 1

        for p in all_passports:
            if p.get("contract_id") == contract_id and p.get("passport_id"):
                passports.delete(p["passport_id"])
                counts["legal_passports"] += 1

        for f in all_findings:
            if f.get("contract_id") == contract_id and f.get("id"):
                findings.delete(f["id"])
                counts["risk_findings"] += 1

        for pr in all_proposals:
            if pr.get("contract_id") == contract_id and pr.get("id"):
                redline_proposals.delete(pr["id"])
                counts["redline_proposals"] += 1

        contracts.delete(contract_id)
        counts["contracts"] += 1

    print("\nDone. Deleted:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    if left_locked:
        print(f"\n{len(left_locked)} evidence_records could not be deleted (anchored after all, lock kicked in mid-run): {left_locked}")
        print("Their parent contract/version/passport docs were still deleted above; these evidence rows are now orphaned but harmless.")


if __name__ == "__main__":
    main()
