r"""Backfill verification_snapshot.evidence_items on pre-snapshot passports.

Passports published before the integrity snapshot fix can show a false FAIL
when later evidence (anchoring, countersignatures) is appended. The live
verifier now ignores post-publish appends, but persisting the publish-time
evidence list makes the check use the same snapshot path as new passports.

Dry-run by default. Writes only when the as-of-publish evidence hash already
matches the stored evidence_hash — it never rewrites hashes.

Run from backend/ with the project venv:
    .\.venv\Scripts\python.exe scripts\repair_passport_integrity_snapshots.py
    .\.venv\Scripts\python.exe scripts\repair_passport_integrity_snapshots.py --apply
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.domains.passport.integrity import evidence_as_of_publish, verify_passport_integrity
from app.lexproof.repositories.firestore import FirestoreRepository


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill passport evidence snapshots when the hash already matches.")
    parser.add_argument("--apply", action="store_true", help="Write matching snapshots to Firestore. Default is dry-run.")
    args = parser.parse_args()

    settings = get_settings()
    passports = FirestoreRepository("legal_passports", settings=settings)
    evidence = FirestoreRepository("evidence_records", settings=settings)
    live_by_passport: dict[str, list[dict[str, Any]]] = {}
    for record in evidence.stream():
        passport_id = str(record.get("passport_id") or "")
        if passport_id:
            live_by_passport.setdefault(passport_id, []).append(record)

    repaired = 0
    skipped = 0
    mismatched = 0
    already_snapshotted = 0

    for passport in passports.stream():
        passport_id = str(passport.get("passport_id") or passport.get("id") or "")
        if not passport_id:
            skipped += 1
            continue
        metadata = dict(passport.get("metadata") or {})
        snapshot = dict(metadata.get("verification_snapshot") or {})
        if snapshot.get("evidence_items") is not None:
            already_snapshotted += 1
            continue

        as_of = evidence_as_of_publish(live_by_passport.get(passport_id, []), passport.get("created_at"))
        if not as_of:
            skipped += 1
            print(f"SKIP empty as-of-publish evidence: {passport_id}")
            continue
        result = verify_passport_integrity(passport, evidence_items=as_of)
        if not result.get("evidence_verified"):
            mismatched += 1
            print(f"SKIP hash mismatch: {passport_id}")
            continue

        snapshot["evidence_items"] = _json_safe(as_of)
        metadata["verification_snapshot"] = snapshot
        if args.apply:
            passports.set(passport_id, {"metadata": metadata}, merge=True)
            print(f"REPAIRED {passport_id} ({len(as_of)} evidence items)")
        else:
            print(f"WOULD REPAIR {passport_id} ({len(as_of)} evidence items)")
        repaired += 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print("---", mode, "---")
    print("repaired:", repaired)
    print("already snapshotted:", already_snapshotted)
    print("hash mismatch:", mismatched)
    print("skipped:", skipped)


if __name__ == "__main__":
    main()
