"""Public PayPal sandbox webhook. No Firebase auth and no read-only UID gate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings
from ..repositories.firestore import FirestoreRepository
from ..services.paypal.auth import PayPalTokenProvider
from ..services.paypal.webhooks import VERIFY_URL, PayPalWebhookError, handle_paypal_webhook

router = APIRouter(tags=["paypal-webhooks"])


def _repos() -> dict[str, FirestoreRepository]:
    return {
        "invoices": FirestoreRepository("payment_invoices"),
        "obligations": FirestoreRepository("payment_obligations"),
        "receipts": FirestoreRepository("payment_receipts"),
        "events": FirestoreRepository("payment_webhook_events"),
        "evidence": FirestoreRepository("evidence_records"),
        "passports": FirestoreRepository("legal_passports"),
    }


async def verify_with_paypal(headers: dict[str, str], event: dict[str, Any]) -> str:
    settings = get_settings()
    if not settings.has_paypal_configuration():
        raise PayPalWebhookError(503, "PayPal is not configured")
    provider = PayPalTokenProvider(
        settings.paypal_client_id,
        settings.paypal_client_secret.get_secret_value(),
    )
    body = {
        "auth_algo": headers["paypal-auth-algo"],
        "cert_url": headers["paypal-cert-url"],
        "transmission_id": headers["paypal-transmission-id"],
        "transmission_sig": headers["paypal-transmission-sig"],
        "transmission_time": headers["paypal-transmission-time"],
        "webhook_id": settings.paypal_webhook_id,
        "webhook_event": event,
    }
    try:
        response = await provider.request("POST", VERIFY_URL, json=body, timeout=4.0)
    finally:
        await provider.aclose()
    if response.status_code != 200:
        return "FAILURE"
    try:
        payload = response.json()
    except Exception:
        return "FAILURE"
    if not isinstance(payload, dict):
        return "FAILURE"
    return str(payload.get("verification_status") or "FAILURE")


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body()
    settings = get_settings()
    try:
        return await handle_paypal_webhook(
            raw,
            dict(request.headers),
            webhook_id=settings.paypal_webhook_id,
            verify=verify_with_paypal,
            **_repos(),
        )
    except PayPalWebhookError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
