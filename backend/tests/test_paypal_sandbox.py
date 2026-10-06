"""Sandbox PayPal path. Skipped unless RUN_PAYPAL_SANDBOX=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytestmark = pytest.mark.paypal_sandbox
SANDBOX = os.getenv("RUN_PAYPAL_SANDBOX") == "1"


@pytest.mark.skipif(not SANDBOX, reason="set RUN_PAYPAL_SANDBOX=1 to call the PayPal sandbox")
@pytest.mark.asyncio
async def test_create_send_then_refund_executes_once():
    from app.lexproof.config import get_settings
    from app.lexproof.services.paypal.actions import PaymentActions
    from app.lexproof.services.paypal.agent import call_paypal_tool
    from app.lexproof.services.paypal.auth import PayPalTokenProvider
    from app.lexproof.services.paypal.guard import ApprovedObligation, GuardDecision, decide
    from app.lexproof.services.paypal.ledger import record_tool_result
    from paypal_memory import MemoryRepository

    settings = get_settings()
    if not settings.has_paypal_configuration():
        pytest.skip("PayPal sandbox credentials are not configured")
    provider = PayPalTokenProvider(settings.paypal_client_id, settings.paypal_client_secret.get_secret_value())
    invoices = MemoryRepository()
    obligations = MemoryRepository()
    receipts = MemoryRepository()
    evidence = MemoryRepository()
    passports = MemoryRepository()
    obligations.set(
        "ob-1",
        {"id": "ob-1", "status": "APPROVED", "amount": "1.00", "currency": "USD", "payer_email": "sb-tdpzh53193435@personal.example.com"},
    )
    try:
        token = await provider.get_access_token()
        create_args = {
            "currency_code": "USD",
            "note": "LexProof sandbox smoke",
            "primary_recipients": [{"billing_info": {"email_address": "sb-tdpzh53193435@personal.example.com"}}],
            "items": [{"name": "Kickoff", "quantity": "1", "unit_amount": {"currency_code": "USD", "value": "1.00"}}],
        }
        decision = decide(
            "create_invoice",
            create_args,
            [ApprovedObligation("ob-1", "USD", "1.00", "sb-tdpzh53193435@personal.example.com", "APPROVED")],
            set(),
        )
        assert decision.decision == "allow"
        created = await call_paypal_tool(settings.paypal_mcp_url, token.access_token, "create_invoice", create_args)
        record_tool_result(
            invoices=invoices,
            obligations=obligations,
            receipts=receipts,
            evidence=evidence,
            passports=passports,
            org_id="sandbox",
            contract_id="sandbox",
            actor="sandbox",
            tool="create_invoice",
            args=create_args,
            response=created,
            decision=decision,
            receipt={"tool": "create_invoice"},
        )
        invoice_id = next(iter(invoices.docs))
        send_decision = decide("send_invoice", {"invoice_id": invoice_id}, [], set(), __import__("app.lexproof.services.paypal.ledger", fromlist=["load_ledger"]).load_ledger(invoices, obligations, "sandbox"))
        assert send_decision.decision == "allow"
        sent = await call_paypal_tool(settings.paypal_mcp_url, token.access_token, "send_invoice", {"invoice_id": invoice_id})

        async def fetch(name: str, args: dict) -> dict:
            return await call_paypal_tool(settings.paypal_mcp_url, token.access_token, name, args)

        from app.lexproof.services.paypal.ledger import confirm_tool_result

        sent, issue = await confirm_tool_result("send_invoice", {"invoice_id": invoice_id}, sent, fetch)
        assert issue is None
        record_tool_result(
            invoices=invoices,
            obligations=obligations,
            receipts=receipts,
            evidence=evidence,
            passports=passports,
            org_id="sandbox",
            contract_id="sandbox",
            actor="sandbox",
            tool="send_invoice",
            args={"invoice_id": invoice_id},
            response=sent,
            decision=send_decision,
            receipt={"tool": "send_invoice"},
        )
        assert invoices.get(invoice_id)["status"] == "SENT"
        refund_args = {"invoice_id": invoice_id}
        blocked = decide("create_refund", refund_args, [], set())
        assert blocked.decision == "needs_approval"
        calls = {"n": 0}

        async def call_tool(tool: str, args: dict) -> dict:
            calls["n"] += 1
            return await call_paypal_tool(settings.paypal_mcp_url, token.access_token, tool, args)

        from app.lexproof.services.workflow_engine import WorkflowEngine

        definitions = MemoryRepository()
        instances = MemoryRepository()
        histories: dict[str, MemoryRepository] = {}
        actions = PaymentActions(
            actions=MemoryRepository(),
            invoices=invoices,
            obligations=obligations,
            receipts=receipts,
            evidence=evidence,
            passports=passports,
            workflow=WorkflowEngine(definitions=definitions, instances=instances, history_factory=lambda item: histories.setdefault(item, MemoryRepository())),
            call_tool=call_tool,
        )
        opened = actions.open_request(org_id="sandbox", contract_id="sandbox", tool="create_refund", args=refund_args, requested_by="owner", reason=blocked.reason)
        actions.transition(opened["id"], "approve", "approver", ["approver"])
        await actions.execute(opened["id"], "approver", ["approver"])
        with pytest.raises(Exception) as again:
            await actions.execute(opened["id"], "approver", ["approver"])
        assert getattr(again.value, "status_code", None) == 409
        assert calls["n"] == 1
    finally:
        await provider.aclose()
