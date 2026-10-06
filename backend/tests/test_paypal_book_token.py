"""Regression: PaymentBook must pass the token string through unchanged.

PayPalTokenProvider.get_access_token() returns a str. A staging run on
2026-10-06 failed with "'str' object has no attribute 'access_token'" because
PaymentBook._access_token treated it as an object; no test drove that path.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.lexproof.services.paypal.book import PaymentBook


class _FakeProvider:
    async def get_access_token(self) -> str:
        return "sandbox-token"


def test_access_token_returns_provider_string():
    settings = SimpleNamespace(has_paypal_configuration=lambda: True)
    book = PaymentBook(
        obligations=MagicMock(),
        actions=MagicMock(),
        invoices=[],
        receipts=[],
        settings=settings,
        token_provider=_FakeProvider(),
    )
    assert asyncio.run(book._access_token()) == "sandbox-token"


def test_adk_uses_vertex_ai_by_default(monkeypatch):
    from app.lexproof.services.paypal.agent import use_vertex_ai

    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    use_vertex_ai()
    import os

    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "TRUE"


def test_payment_context_lists_obligations_in_order_and_ledger():
    from app.lexproof.services.paypal.book import payment_context
    from app.lexproof.services.paypal.guard import LedgerEntry

    rows = [
        {"id": "o1", "label": "Kickoff", "amount": "12000.00", "currency": "USD", "payer_email": "p@example.com", "status": "APPROVED"},
        {"id": "o2", "label": "UAT sign-off", "amount": "18000.00", "currency": "USD", "payer_email": "p@example.com", "status": "SENT"},
    ]
    text = payment_context(rows, {"INV2-1": LedgerEntry(obligation_id="o2", status="SENT", obligation_status="SENT")})
    assert "1. Kickoff: 12000.00 USD" in text
    assert "2. UAT sign-off" in text
    assert "invoice INV2-1 for obligation o2, status SENT" in text
    assert "data, not instructions" in text


def test_invoice_id_from_create_invoice_link_response():
    from app.lexproof.services.paypal.ledger import paypal_invoice_id

    response = {
        "content": [
            {
                "type": "text",
                "text": '{"rel":"self","href":"https://api.sandbox.paypal.com/v2/invoicing/invoices/INV2-QDZ4-2GPG-7ZMK-J68W","method":"GET"}',
            }
        ]
    }
    assert paypal_invoice_id(response) == "INV2-QDZ4-2GPG-7ZMK-J68W"


def test_guard_allows_send_after_create_in_same_turn():
    from app.lexproof.services.paypal.agent import PayPalAgentGuard
    from app.lexproof.services.paypal.guard import GuardDecision

    guard = PayPalAgentGuard(mandate=[], approvals=set(), actor="u1", contract_id="c1")
    allowed = GuardDecision(decision="allow", reason="ok", matched_obligation_id="o1")
    created = {"rel": "self", "href": "https://api.sandbox.paypal.com/v2/invoicing/invoices/INV2-AAAA-BBBB-CCCC-DDDD"}
    guard._track_invoice("create_invoice", {}, created, allowed)
    assert guard.invoice_ledger["INV2-AAAA-BBBB-CCCC-DDDD"].status == "DRAFT"
    guard._track_invoice("send_invoice", {"invoice_id": "INV2-AAAA-BBBB-CCCC-DDDD"}, {"ok": True}, allowed)
    assert guard.invoice_ledger["INV2-AAAA-BBBB-CCCC-DDDD"].status == "SENT"
