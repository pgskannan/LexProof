"""Cancel DRAFT and SENT sandbox invoices created for the PayPal demo contract.

Does not call live PayPal. Idempotent: invoices already cancelled are skipped.
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


async def reset(org_id: str) -> None:
    settings = get_settings()
    if not settings.has_paypal_configuration() or settings.paypal_env.strip().lower() != "sandbox":
        raise SystemExit("PayPal sandbox credentials are required")
    contracts = FirestoreRepository("contracts")
    invoices = FirestoreRepository("payment_invoices")
    matches = [item for item in contracts.stream() if item.get("org_id") == org_id and item.get("name") == DEMO_TITLE]
    if not matches:
        print("no demo contract")
        return
    contract_id = matches[0].get("id")
    provider = PayPalTokenProvider(settings.paypal_client_id, settings.paypal_client_secret.get_secret_value())
    try:
        for invoice in invoices.stream():
            if invoice.get("contract_id") != contract_id:
                continue
            status = str(invoice.get("status") or "").upper()
            if status not in {"DRAFT", "SENT"}:
                continue
            invoice_id = str(invoice.get("invoice_id") or invoice.get("id"))
            if status == "DRAFT":
                response = await provider.request("DELETE", f"{SANDBOX_API}/v2/invoicing/invoices/{invoice_id}")
            else:
                response = await provider.request(
                    "POST",
                    f"{SANDBOX_API}/v2/invoicing/invoices/{invoice_id}/cancel",
                    json={"subject": "Demo reset", "note": "LexProof sandbox demo reset", "send_to_invoicer": False, "send_to_recipient": False},
                )
            if response.status_code not in {200, 204, 404, 422}:
                print(f"skip {invoice_id} paypal status {response.status_code}")
                continue
            invoices.set(invoice_id, {"status": "CANCELLED"}, merge=True)
            print(f"cancelled {invoice_id}")
    finally:
        await provider.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=True)
    args = parser.parse_args()
    asyncio.run(reset(args.org_id))


if __name__ == "__main__":
    main()
