"""Idempotent PayPal sandbox demo: MSA, three approved milestones, unapproved bonus.

Usage (from backend/):
  python scripts/seed_paypal_demo.py --org-id ORG --owner-id UID --approver-id UID
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.services.paypal.obligations import PaymentObligations, assess_extracted_obligation
from scripts.paypal_demo_contract import (
    DEMO_CONTRACT_TEXT,
    DEMO_TITLE,
    INJECTION,
    MILESTONES,
    PAYER_EMAIL,
    write_demo_docx,
)


def _find_contract(contracts: FirestoreRepository, org_id: str) -> dict | None:
    matches = [item for item in contracts.stream() if item.get("org_id") == org_id and item.get("name") == DEMO_TITLE]
    return matches[0] if matches else None


async def seed(org_id: str, owner_id: str, approver_id: str) -> None:
    if owner_id == approver_id:
        raise SystemExit("owner and approver must be different people")
    docx = write_demo_docx()
    contracts = FirestoreRepository("contracts")
    versions = FirestoreRepository("contract_versions")
    obligations = PaymentObligations(contracts=contracts, versions=versions)
    existing = _find_contract(contracts, org_id)
    if existing:
        contract_id = existing.get("id") or existing.get("contract_id")
        print(f"contract exists {contract_id}")
    else:
        contract_id = str(uuid4())
        version_id = str(uuid4())
        content_hash = hashlib.sha256(DEMO_CONTRACT_TEXT.encode("utf-8")).hexdigest()
        contracts.set(contract_id, {"id": contract_id, "org_id": org_id, "name": DEMO_TITLE, "owner_id": owner_id, "content_hash": content_hash})
        versions.set(
            version_id,
            {
                "id": version_id,
                "contract_id": contract_id,
                "org_id": org_id,
                "is_current": True,
                "version_number": 1,
                "content_hash": content_hash,
                "document_text": DEMO_CONTRACT_TEXT,
                "filename": docx.name,
            },
        )
        print(f"created contract {contract_id}")

    owner = {"uid": owner_id}
    approver = {"uid": approver_id}
    current = obligations._rows(org_id, contract_id)
    by_label = {item.get("label"): item for item in current}
    version = obligations._current_version(contract_id) or {}
    contract_hash = str(version.get("content_hash") or "")
    for milestone in MILESTONES:
        if milestone["label"] in by_label:
            print(f"obligation exists {milestone['label']}")
            continue
        assessed = assess_extracted_obligation(DEMO_CONTRACT_TEXT, {**milestone, "currency": "USD", "payer_email": PAYER_EMAIL, "payer_name": "Acme Retail Inc."})
        obligation_id = str(uuid4())
        obligations.obligations.set(
            obligation_id,
            {
                "id": obligation_id,
                "org_id": org_id,
                "contract_id": contract_id,
                "contract_version_id": version.get("id"),
                "contract_hash": contract_hash,
                "status": "EXTRACTED",
                "extracted_by": "seed:paypal-obligations-v1",
                "edited_by": None,
                "approved_by": None,
                "created_at": "2026-10-12T00:00:00+00:00",
                "updated_at": "2026-10-12T00:00:00+00:00",
                **assessed,
            },
        )
        obligations.edit(obligation_id, owner, {"payer_email": PAYER_EMAIL})
        obligations.approve(obligation_id, approver)
        print(f"approved {milestone['label']} {obligation_id}")
    if INJECTION["label"] not in by_label:
        assessed = assess_extracted_obligation(DEMO_CONTRACT_TEXT, {**INJECTION, "currency": "USD", "payer_name": "Acme Retail Inc."})
        assessed["needs_review_reason"] = INJECTION["needs_review_reason"]
        obligation_id = str(uuid4())
        obligations.obligations.set(
            obligation_id,
            {
                "id": obligation_id,
                "org_id": org_id,
                "contract_id": contract_id,
                "contract_version_id": version.get("id"),
                "contract_hash": contract_hash,
                "status": "EXTRACTED",
                "extracted_by": "seed:paypal-obligations-v1",
                "edited_by": None,
                "approved_by": None,
                "created_at": "2026-10-12T00:00:00+00:00",
                "updated_at": "2026-10-12T00:00:00+00:00",
                **assessed,
            },
        )
        print(f"left unapproved {INJECTION['label']} {obligation_id}")
    print(f"docx {docx}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--approver-id", required=True)
    args = parser.parse_args()
    asyncio.run(seed(args.org_id, args.owner_id, args.approver_id))


if __name__ == "__main__":
    main()
