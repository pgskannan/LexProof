"""Dry-run or anchor one append-only PayPal receipt-chain checkpoint."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.services.paypal.checkpoint_service import create_payment_checkpoint, payment_chain_snapshot


async def anchor_checkpoint(org_id: str, contract_id: str, confirm: bool) -> None:
    settings = get_settings()
    contracts = FirestoreRepository("contracts", settings=settings)
    contract = contracts.get(contract_id)
    if not contract or str(contract.get("org_id") or "") != org_id:
        raise SystemExit("Contract not found in the specified organization")

    receipts = FirestoreRepository("payment_receipts", settings=settings)
    checkpoints = FirestoreRepository("payment_checkpoints", settings=settings)
    evidence = FirestoreRepository("evidence_records", settings=settings)
    passports = FirestoreRepository("legal_passports", settings=settings)
    _, head, count = payment_chain_snapshot(contract_id, org_id, receipts)
    prior = [
        item for item in checkpoints.stream()
        if item.get("org_id") == org_id and item.get("contract_id") == contract_id
    ]
    previous_count = max((int(item.get("count") or 0) for item in prior), default=0)
    if not confirm:
        print(f"receipt count: {count}")
        print(f"chain_head: {head}")
        print(f"new receipts: {max(0, count - previous_count)}")
        print("dry-run; pass --confirm to create and anchor one checkpoint")
        return
    result = await create_payment_checkpoint(
        contract_id=contract_id,
        org_id=org_id,
        actor_id="operator:anchor_payment_checkpoint",
        receipts=receipts,
        checkpoints=checkpoints,
        evidence=evidence,
        passports=passports,
        settings=settings,
    )
    print(f"checkpoint: {result['id']}")
    print(f"transaction_hash: {result['transaction_hash']}")
    print(f"block_number: {result['block_number']}")
    print(f"receipt count: {result['count']}")
    print(f"chain_head: {result['chain_head']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--confirm", action="store_true", help="Submit one real Sepolia checkpoint transaction")
    args = parser.parse_args()
    asyncio.run(anchor_checkpoint(args.org_id, args.contract_id, args.confirm))


if __name__ == "__main__":
    main()