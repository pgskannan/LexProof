"""Create or update the sandbox PayPal webhook and print its id once.

The id is the only value printed. Put it in PAYPAL_WEBHOOK_ID / Secret Manager
as lexproof-paypal-webhook-id, then redeploy the staging service.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.lexproof.config import get_settings
from app.lexproof.services.paypal.auth import PayPalTokenProvider

EVENT_TYPES = (
    "INVOICING.INVOICE.PAID",
    "INVOICING.INVOICE.CANCELLED",
    "INVOICING.INVOICE.REFUNDED",
    "PAYMENT.CAPTURE.COMPLETED",
    "PAYMENT.CAPTURE.REFUNDED",
)
LIST_URL = "https://api-m.sandbox.paypal.com/v1/notifications/webhooks"


def _types() -> list[dict[str, str]]:
    return [{"name": name} for name in EVENT_TYPES]


async def register(url: str) -> str:
    settings = get_settings()
    if not settings.has_paypal_configuration():
        raise SystemExit("PayPal sandbox credentials are not configured")
    provider = PayPalTokenProvider(settings.paypal_client_id, settings.paypal_client_secret.get_secret_value())
    try:
        listed = await provider.request("GET", LIST_URL)
        if listed.status_code != 200:
            raise SystemExit(f"PayPal webhook list failed with status {listed.status_code}")
        existing = listed.json().get("webhooks") or []
        match = next((item for item in existing if item.get("url") == url), None)
        if match:
            webhook_id = str(match["id"])
            updated = await provider.request(
                "PATCH",
                f"{LIST_URL}/{webhook_id}",
                json=[
                    {"op": "replace", "path": "/url", "value": url},
                    {"op": "replace", "path": "/event_types", "value": _types()},
                ],
            )
            if updated.status_code not in (200, 204):
                raise SystemExit(f"PayPal webhook update failed with status {updated.status_code}")
            return webhook_id
        created = await provider.request("POST", LIST_URL, json={"url": url, "event_types": _types()})
        if created.status_code not in (200, 201):
            raise SystemExit(f"PayPal webhook create failed with status {created.status_code}")
        body = created.json()
        webhook_id = str(body.get("id") or "")
        if not webhook_id:
            raise SystemExit("PayPal webhook create did not return an id")
        return webhook_id
    finally:
        await provider.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the LexProof sandbox PayPal webhook")
    parser.add_argument("--url", required=True, help="Public https URL PayPal will call")
    args = parser.parse_args()
    if not args.url.startswith("https://"):
        raise SystemExit("--url must be https")
    webhook_id = asyncio.run(register(args.url))
    # The id is not a secret. The client secret is never printed.
    print(json.dumps({"webhook_id": webhook_id}))


if __name__ == "__main__":
    main()
