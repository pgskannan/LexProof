"""PayPal sandbox webhooks move the ledger to PAID, CANCELLED, or REFUNDED.

Verification uses PayPal's verify-webhook-signature API. The raw event is not
stored. A repeated event id is acknowledged and does not change state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable
from uuid import uuid4

from ...services.audit import record_audit_event
from .auth import SANDBOX_API_HOST
from .evidence_record import _passport_id, write_payment_evidence
from .receipts import canonical_json, receipt_hash

VERIFY_URL = f"https://{SANDBOX_API_HOST}/v1/notifications/verify-webhook-signature"
EVENTS = "payment_webhook_events"

_STATUS_BY_EVENT = {
    "INVOICING.INVOICE.PAID": "PAID",
    "INVOICING.INVOICE.CANCELLED": "CANCELLED",
    "INVOICING.INVOICE.REFUNDED": "REFUNDED",
    "PAYMENT.CAPTURE.COMPLETED": "PAID",
    "PAYMENT.CAPTURE.REFUNDED": "REFUNDED",
}
_HEADER_NAMES = (
    "paypal-auth-algo",
    "paypal-cert-url",
    "paypal-transmission-id",
    "paypal-transmission-sig",
    "paypal-transmission-time",
)


class PayPalWebhookError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


VerifyCall = Callable[[dict[str, str], dict[str, Any]], Awaitable[str]]


async def handle_paypal_webhook(
    raw_body: bytes,
    headers: dict[str, str],
    *,
    webhook_id: str,
    invoices: Any,
    obligations: Any,
    receipts: Any,
    events: Any,
    evidence: Any,
    passports: Any,
    verify: VerifyCall,
    audit: Callable[..., None] = record_audit_event,
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Verify one event and apply it. Duplicate ids return without writes."""
    if not webhook_id.strip():
        raise PayPalWebhookError(503, "PayPal webhook id is not configured")
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PayPalWebhookError(400, "PayPal webhook body was not JSON") from exc
    if not isinstance(event, dict):
        raise PayPalWebhookError(400, "PayPal webhook body was not an object")
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("event_type") or "").strip()
    if not event_id or not event_type:
        raise PayPalWebhookError(400, "PayPal webhook is missing id or event_type")
    transmission = _transmission_headers(headers)
    status = await verify(transmission, event)
    if status != "SUCCESS":
        audit(
            actor_id="paypal_webhook",
            action="paypal_webhook_rejected",
            resource_type="payment_webhook_event",
            resource_id=event_id,
            summary="PayPal webhook verification_status was not SUCCESS",
            metadata={"event_type": event_type, "verification_status": status},
        )
        raise PayPalWebhookError(400, "PayPal webhook signature verification failed")
    if events.get(event_id):
        return {"ok": True, "duplicate": True, "event_id": event_id}

    stamp = clock() if clock else datetime.now(timezone.utc).isoformat()
    invoice_id = _matching_invoice_id(event, invoices)
    invoice = invoices.get(invoice_id) if invoice_id else None
    if invoice is None or event_type not in _STATUS_BY_EVENT:
        events.set(
            event_id,
            {
                "id": event_id,
                "event_type": event_type,
                "status": "unmatched",
                "invoice_id": invoice_id,
                "created_at": stamp,
            },
        )
        audit(
            actor_id="paypal_webhook",
            action="paypal_webhook_unmatched",
            resource_type="payment_webhook_event",
            resource_id=event_id,
            summary="unmatched",
            metadata={"event_type": event_type, "invoice_id": invoice_id},
        )
        return {"ok": True, "event_id": event_id, "status": "unmatched"}

    target = _STATUS_BY_EVENT[event_type]
    amount = _amount(event.get("resource"))
    obligation_id = str(invoice.get("obligation_id") or "")
    obligation = obligations.get(obligation_id) if obligation_id else None
    obligation_status, ledger_status = _statuses(target, amount, obligation, invoice)
    linked_passport = _passport_id(passports, str(invoice.get("contract_id") or ""))

    def apply(transaction: Any) -> str | None:
        if events.get(event_id, transaction=transaction):
            return "duplicate"
        current = invoices.get(invoice_id, transaction=transaction) if invoice_id else None
        if not current:
            return "unmatched"
        receipt_body = {
            "actor": "paypal_webhook",
            "amount": format(amount, "f") if amount is not None else "",
            "contract_id": str(invoice.get("contract_id") or ""),
            "currency": str((obligation or invoice).get("currency") or ""),
            "decision": "allow",
            "event_id": event_id,
            "resource_id": invoice_id or "",
            "source": "paypal_webhook",
            "time": stamp,
            "tool": event_type,
        }
        digest = receipt_hash(receipt_body)
        receipt_id = str(uuid4())
        evidence_id = write_payment_evidence(
            evidence=evidence,
            passports=passports,
            org_id=str(invoice.get("org_id") or ""),
            contract_id=str(invoice.get("contract_id") or ""),
            actor_id="paypal_webhook",
            title=f"PayPal webhook {event_type}",
            content={"receipt_hash": digest, "event_id": event_id, "resource_id": invoice_id, "source": "paypal_webhook"},
            source_id=receipt_id,
            now=lambda: stamp,
            transaction=transaction,
            passport_id=linked_passport,
        )
        receipts.set(
            receipt_id,
            {
                **receipt_body,
                "id": receipt_id,
                "org_id": invoice.get("org_id"),
                "receipt_hash": digest,
                "evidence_id": evidence_id,
                "created_at": stamp,
                "canonical": canonical_json(receipt_body),
            },
            transaction=transaction,
        )
        if invoice_id:
            invoices.set(
                invoice_id,
                {"status": ledger_status, "updated_at": stamp, "webhook_event_id": event_id},
                merge=True,
                transaction=transaction,
            )
        if obligation_id:
            obligations.set(
                obligation_id,
                {"status": obligation_status, "updated_at": stamp},
                merge=True,
                transaction=transaction,
            )
        events.set(
            event_id,
            {
                "id": event_id,
                "event_type": event_type,
                "status": obligation_status,
                "invoice_id": invoice_id,
                "receipt_id": receipt_id,
                "org_id": invoice.get("org_id"),
                "contract_id": invoice.get("contract_id"),
                "created_at": stamp,
            },
            transaction=transaction,
        )
        return receipt_id

    outcome = invoices.run_transaction(apply) if hasattr(invoices, "run_transaction") else apply(None)
    if outcome == "duplicate":
        return {"ok": True, "duplicate": True, "event_id": event_id}
    if outcome == "unmatched":
        events.set(event_id, {"id": event_id, "event_type": event_type, "status": "unmatched", "invoice_id": invoice_id, "created_at": stamp})
        audit(
            actor_id="paypal_webhook",
            action="paypal_webhook_unmatched",
            resource_type="payment_webhook_event",
            resource_id=event_id,
            summary="unmatched",
            metadata={"event_type": event_type, "invoice_id": invoice_id},
        )
        return {"ok": True, "event_id": event_id, "status": "unmatched"}
    return {"ok": True, "event_id": event_id, "status": obligation_status, "receipt_id": outcome}


def _transmission_headers(headers: dict[str, str]) -> dict[str, str]:
    folded = {str(key).lower(): str(value) for key, value in headers.items()}
    missing = [name for name in _HEADER_NAMES if not folded.get(name, "").strip()]
    if missing:
        raise PayPalWebhookError(400, "PayPal webhook is missing transmission headers")
    cert_url = folded["paypal-cert-url"]
    if not cert_url.startswith("https://") or "paypal.com" not in cert_url:
        raise PayPalWebhookError(400, "PayPal webhook certificate URL is not a PayPal https URL")
    return {name: folded[name] for name in _HEADER_NAMES}


def _matching_invoice_id(event: dict[str, Any], invoices: Any) -> str | None:
    preferred: list[str] = []
    other: list[str] = []

    def walk(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                walk(child, key)
            return
        if isinstance(value, str) and key in {"invoice_id", "id", "order_id"} and value.strip():
            bucket = preferred if key == "invoice_id" else other
            bucket.append(value.strip())

    walk(event.get("resource"))
    seen: list[str] = []
    for candidate in preferred + other:
        if candidate not in seen:
            seen.append(candidate)
    for candidate in seen:
        if invoices.get(candidate):
            return candidate
    return seen[0] if seen else None


def _amount(resource: Any) -> Decimal | None:
    found: list[Decimal] = []

    def walk(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                walk(child)
            return
        if key in {"value", "total", "amount"} and value is not None:
            try:
                parsed = Decimal(str(value).replace(",", "").replace("$", ""))
            except (InvalidOperation, ValueError):
                return
            if parsed.is_finite() and parsed >= 0:
                found.append(parsed)

    walk(resource)
    return found[0] if found else None


def _statuses(target: str, amount: Decimal | None, obligation: dict[str, Any] | None, invoice: dict[str, Any]) -> tuple[str, str]:
    if target != "REFUNDED":
        return target, target
    try:
        original = Decimal(str((obligation or {}).get("amount") or invoice.get("amount") or "0").replace(",", ""))
    except (InvalidOperation, ValueError):
        original = Decimal(0)
    if amount is not None and original > 0 and amount < original:
        return "PARTIALLY_REFUNDED", str(invoice.get("status") or "SENT")
    return "REFUNDED", "REFUNDED"
