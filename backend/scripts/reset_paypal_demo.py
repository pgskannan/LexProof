"""Reset the PayPal sandbox demo contract.

Dry-run unless ``--confirm`` is passed. Cancels DRAFT and SENT sandbox invoices
for the contract (a DRAFT that cannot be cancelled is deleted), marks those
ledger rows CANCELLED, and sets the demo milestones back to APPROVED. The
Bonus obligation stays EXTRACTED.

Does not call live PayPal.
"""

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
from app.lexproof.services.paypal.auth import PayPalTokenProvider
from scripts.paypal_demo_contract import DEMO_TITLE

SANDBOX_API = "https://api-m.sandbox.paypal.com"
CANCEL_BODY = {
    "subject": "Demo reset",
    "note": "LexProof sandbox demo reset",
    "send_to_invoicer": False,
    "send_to_recipient": False,
}


def _contract(contracts: FirestoreRepository, org_id: str, contract_id: str | None) -> dict | None:
    rows = [item for item in contracts.stream() if item.get("org_id") == org_id]
    if contract_id:
        return next((item for item in rows if item.get("id") == contract_id), None)
    matches = [item for item in rows if item.get("name") == DEMO_TITLE]
    return matches[0] if matches else None


async def _cancel_remote(provider: PayPalTokenProvider, invoice_id: str, status: str) -> int:
    if status == "DRAFT":
        deleted = await provider.request("DELETE", f"{SANDBOX_API}/v2/invoicing/invoices/{invoice_id}")
        if deleted.status_code in {200, 204, 404}:
            return deleted.status_code
    cancelled = await provider.request("POST", f"{SANDBOX_API}/v2/invoicing/invoices/{invoice_id}/cancel", json=CANCEL_BODY)
    if cancelled.status_code in {200, 204, 404}:
        return cancelled.status_code
    if status != "DRAFT" and cancelled.status_code in {405, 422}:
        deleted = await provider.request("DELETE", f"{SANDBOX_API}/v2/invoicing/invoices/{invoice_id}")
        return deleted.status_code
    return cancelled.status_code


async def reset(org_id: str, contract_id: str | None, confirm: bool) -> None:
    settings = get_settings()
    if not settings.has_paypal_configuration() or settings.paypal_env.strip().lower() != "sandbox":
        raise SystemExit("PayPal sandbox credentials are required")
    contracts = FirestoreRepository("contracts")
    invoices = FirestoreRepository("payment_invoices")
    obligations = FirestoreRepository("payment_obligations")
    contract = _contract(contracts, org_id, contract_id)
    if not contract:
        print("no demo contract")
        return
    contract_id = str(contract.get("id"))
    print(f"contract {contract_id} {contract.get('name')}")
    targets = []
    for invoice in invoices.stream():
        if invoice.get("contract_id") != contract_id:
            continue
        status = str(invoice.get("status") or "").upper()
        if status not in {"DRAFT", "SENT"}:
            continue
        invoice_id = str(invoice.get("invoice_id") or invoice.get("id"))
        targets.append((invoice_id, status))
    for invoice_id, status in targets:
        print(f"{'cancel' if confirm else 'would cancel'} {invoice_id} ({status})")
    for obligation in obligations.stream():
        if obligation.get("contract_id") != contract_id:
            continue
        label = str(obligation.get("label") or "")
        next_status = "EXTRACTED" if label.strip().lower() == "bonus" else "APPROVED"
        current = str(obligation.get("status") or "")
        if current == next_status:
            print(f"keep {label or obligation.get('id')} {current}")
            continue
        print(f"{'set' if confirm else 'would set'} {label or obligation.get('id')} {current} -> {next_status}")
    if not confirm:
        print("dry-run; pass --confirm to apply")
        return
    provider = PayPalTokenProvider(settings.paypal_client_id, settings.paypal_client_secret.get_secret_value())
    try:
        for invoice_id, status in targets:
            code = await _cancel_remote(provider, invoice_id, status)
            if code not in {200, 204, 404, 422}:
                print(f"skip {invoice_id} paypal status {code}")
                continue
            invoices.set(invoice_id, {"status": "CANCELLED"}, merge=True)
            print(f"cancelled {invoice_id} paypal {code}")
    finally:
        await provider.aclose()
    for obligation in obligations.stream():
        if obligation.get("contract_id") != contract_id:
            continue
        label = str(obligation.get("label") or "")
        next_status = "EXTRACTED" if label.strip().lower() == "bonus" else "APPROVED"
        if str(obligation.get("status") or "") == next_status:
            continue
        obligations.set(str(obligation.get("id")), {"status": next_status, "invoice_id": None}, merge=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--contract-id", default=None)
    parser.add_argument("--confirm", action="store_true", help="Apply PayPal and ledger changes. Without this flag the script only prints.")
    args = parser.parse_args()
    asyncio.run(reset(args.org_id, args.contract_id, args.confirm))


if __name__ == "__main__":
    main()
