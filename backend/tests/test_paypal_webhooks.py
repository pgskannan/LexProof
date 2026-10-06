"""PayPal webhook verification, idempotency, and the public receipt chain."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.lexproof.main import create_app
from app.lexproof.services.paypal.public_chain import mask_email, public_payment_chain
from app.lexproof.services.paypal.receipts import canonical_json
from app.lexproof.services.paypal.startup import paypal_health
from app.lexproof.services.paypal.webhooks import PayPalWebhookError, handle_paypal_webhook
from paypal_memory import MemoryRepository

HEADERS = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "paypal-transmission-id": "transmission-1",
    "paypal-transmission-sig": "sig",
    "paypal-transmission-time": "2026-10-19T00:00:00Z",
}


def _repos():
    return {
        "invoices": MemoryRepository(),
        "obligations": MemoryRepository(),
        "receipts": MemoryRepository(),
        "events": MemoryRepository(),
        "evidence": MemoryRepository(),
        "passports": MemoryRepository(),
    }


def _seed(repos):
    repos["invoices"].set(
        "INV2-1",
        {
            "invoice_id": "INV2-1",
            "obligation_id": "ob-1",
            "contract_id": "c-1",
            "org_id": "org-1",
            "status": "SENT",
            "amount": "12000.00",
            "currency": "USD",
        },
    )
    repos["obligations"].set(
        "ob-1",
        {"id": "ob-1", "amount": "12000.00", "currency": "USD", "status": "SENT", "contract_id": "c-1", "label": "Kickoff"},
    )


def _event(event_id: str, event_type: str, invoice_id: str = "INV2-1", value: str = "12000.00") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "event_type": event_type,
            "resource": {"id": invoice_id, "invoice_id": invoice_id, "amount": {"currency_code": "USD", "value": value}},
        }
    ).encode()


async def _ok(headers, event):
    return "SUCCESS"


@pytest.mark.asyncio
async def test_paid_webhook_is_idempotent_and_writes_a_receipt():
    repos = _repos()
    _seed(repos)
    first = await handle_paypal_webhook(
        _event("WH-1", "INVOICING.INVOICE.PAID"),
        HEADERS,
        webhook_id="hook-1",
        verify=_ok,
        **repos,
    )
    second = await handle_paypal_webhook(
        _event("WH-1", "INVOICING.INVOICE.PAID"),
        HEADERS,
        webhook_id="hook-1",
        verify=_ok,
        **repos,
    )
    assert first["status"] == "PAID"
    assert second["duplicate"] is True
    assert repos["invoices"].get("INV2-1")["status"] == "PAID"
    assert repos["obligations"].get("ob-1")["status"] == "PAID"
    assert len(repos["receipts"].docs) == 1
    receipt = next(iter(repos["receipts"].docs.values()))
    assert receipt["source"] == "paypal_webhook"
    assert receipt["event_id"] == "WH-1"
    assert "links" not in receipt
    assert len(repos["evidence"].docs) == 1


@pytest.mark.asyncio
async def test_failed_verification_is_400_and_audited():
    repos = _repos()
    _seed(repos)
    audits = []

    async def reject(headers, event):
        return "FAILURE"

    with pytest.raises(PayPalWebhookError) as caught:
        await handle_paypal_webhook(
            _event("WH-2", "INVOICING.INVOICE.PAID"),
            HEADERS,
            webhook_id="hook-1",
            verify=reject,
            audit=lambda **kwargs: audits.append(kwargs),
            **repos,
        )
    assert caught.value.status_code == 400
    assert audits[0]["action"] == "paypal_webhook_rejected"
    assert repos["invoices"].get("INV2-1")["status"] == "SENT"
    assert repos["events"].docs == {}


@pytest.mark.asyncio
async def test_unknown_invoice_is_acknowledged_without_a_status_change():
    repos = _repos()
    _seed(repos)
    audits = []
    result = await handle_paypal_webhook(
        _event("WH-3", "INVOICING.INVOICE.PAID", invoice_id="INV2-MISSING"),
        HEADERS,
        webhook_id="hook-1",
        verify=_ok,
        audit=lambda **kwargs: audits.append(kwargs),
        **repos,
    )
    assert result["status"] == "unmatched"
    assert audits[0]["summary"] == "unmatched"
    assert repos["invoices"].get("INV2-1")["status"] == "SENT"
    assert repos["receipts"].docs == {}
    again = await handle_paypal_webhook(
        _event("WH-3", "INVOICING.INVOICE.PAID", invoice_id="INV2-MISSING"),
        HEADERS,
        webhook_id="hook-1",
        verify=_ok,
        audit=lambda **kwargs: audits.append(kwargs),
        **repos,
    )
    assert again["duplicate"] is True
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_partial_refund_does_not_mark_the_obligation_fully_refunded():
    repos = _repos()
    _seed(repos)
    result = await handle_paypal_webhook(
        _event("WH-4", "INVOICING.INVOICE.REFUNDED", value="1.00"),
        HEADERS,
        webhook_id="hook-1",
        verify=_ok,
        **repos,
    )
    assert result["status"] == "PARTIALLY_REFUNDED"
    assert repos["obligations"].get("ob-1")["status"] == "PARTIALLY_REFUNDED"
    assert repos["invoices"].get("INV2-1")["status"] == "SENT"


def test_public_chain_masks_email_and_hashes_the_shown_json():
    repos = _repos()
    repos["passports"].set("pass-1", {"id": "pass-1", "passport_id": "pass-1", "contract_id": "c-1"})
    repos["obligations"].set(
        "ob-1",
        {
            "id": "ob-1",
            "contract_id": "c-1",
            "label": "Kickoff",
            "amount": "12000.00",
            "currency": "USD",
            "status": "PAID",
            "clause_ref": "3.1",
            "payer_email": "sb-tdpzh53193435@personal.example.com",
        },
    )
    repos["receipts"].set(
        "rc-1",
        {
            "id": "rc-1",
            "contract_id": "c-1",
            "tool": "create_invoice",
            "decision": "deny",
            "reason": "no approved obligation",
            "actor": "owner@example.com",
            "created_at": "2026-10-19T00:00:00+00:00",
            "evidence_id": "ev-1",
            "transport": "rest_fallback",
            "mcp_error": "Unsupported cache mode: default",
            "response": {"id": "INV2-SECRET", "links": [{"href": "https://www.sandbox.paypal.com/invoice"}]},
        },
    )
    repos["settings"] = MemoryRepository()
    repos["settings"].set("c-1", {"mandate_hash": "abc123"})
    anchors = MemoryRepository()
    chain = public_payment_chain(
        "pass-1",
        passports=repos["passports"],
        obligations=repos["obligations"],
        receipts=repos["receipts"],
        settings=repos["settings"],
        anchors=anchors,
    )
    assert chain is not None
    assert "payer_email" not in json.dumps(chain["obligations"])
    assert mask_email("sb-tdpzh53193435@personal.example.com") == "s***@personal.example.com"
    shown = chain["receipts"][0]
    assert "INV2-SECRET" not in json.dumps(shown)
    assert "o***@example.com" in shown["canonical"]
    digest = hashlib.sha256(shown["canonical"].encode("utf-8")).hexdigest()
    assert digest == shown["receipt_hash"]
    assert json.loads(shown["canonical"]) == json.loads(canonical_json(json.loads(shown["canonical"])))
    assert shown["anchor_status"] == "pending_checkpoint"
    assert shown["decision"] == "deny"
    assert shown["transport"] == "rest_fallback"
    assert json.loads(shown["canonical"])["transport"] == "rest_fallback"
    assert "mcp_error" not in shown


def test_legacy_public_receipt_keeps_original_canonical_bytes_and_infers_transport():
    repos = _repos()
    repos["passports"].set("pass-1", {"id": "pass-1", "passport_id": "pass-1", "contract_id": "c-1"})
    repos["receipts"].set("rc-legacy", {
        "id": "rc-legacy", "contract_id": "c-1", "tool": "list_invoices",
        "decision": "allow", "actor": "owner", "created_at": "2026-10-01T00:00:00Z",
    })
    chain = public_payment_chain(
        "pass-1", passports=repos["passports"], obligations=MemoryRepository(),
        receipts=repos["receipts"], settings=MemoryRepository(), checkpoints=MemoryRepository(),
    )
    shown = chain["receipts"][0]
    assert shown["transport"] == "mcp"
    assert "transport" not in json.loads(shown["canonical"])


def test_health_paypal_block_has_no_secrets():
    from app.lexproof.config import get_settings

    body = paypal_health(get_settings())
    assert set(body) == {"env", "invoicing_scope"}
    assert body["env"] == "sandbox"
    assert "secret" not in json.dumps(body)


def test_webhook_route_does_not_require_a_firebase_token(monkeypatch):
    monkeypatch.setattr(
        "app.lexproof.api.paypal_webhooks.get_settings",
        lambda: type("Settings", (), {"paypal_webhook_id": ""})(),
    )
    response = TestClient(create_app()).post("/api/webhooks/paypal", content=b"{}")
    assert response.status_code == 503
    assert response.status_code != 401
