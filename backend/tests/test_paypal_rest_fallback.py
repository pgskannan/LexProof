import asyncio
import hashlib
import json

import httpx
import pytest

from app.lexproof.services.paypal.auth import PayPalTokenProvider
from app.lexproof.config import LexProofSettings
from app.lexproof.services.paypal.book import PaymentBook
from app.lexproof.services.paypal.guard import GuardDecision
from app.lexproof.services.paypal.ledger import record_tool_result
from app.lexproof.services.paypal.rest_fallback import (
    call_with_rest_fallback,
    execute_rest_fallback,
    rest_request_for_tool,
)
from app.lexproof.services.paypal.receipts import canonical_json


def test_rest_request_builders_match_each_supported_mcp_tool():
    create_args = {
        "currency_code": "USD",
        "invoice_number": "LP-100",
        "note": "Milestone invoice",
        "primary_recipients": [{"billing_info": {"email_address": "payer@example.com"}}],
        "items": [{"name": "Kickoff", "quantity": "1", "unit_amount": {"currency_code": "USD", "value": "12000.00"}}],
    }
    method, url, body, headers = rest_request_for_tool("create_invoice", create_args)
    assert method == "POST"
    assert url == "https://api-m.sandbox.paypal.com/v2/invoicing/invoices"
    assert body == {
        "detail": {"currency_code": "USD", "invoice_number": "LP-100", "memo": "Milestone invoice"},
        "primary_recipients": create_args["primary_recipients"],
        "items": create_args["items"],
    }
    assert headers["Prefer"] == "return=representation"
    assert headers["PayPal-Request-Id"] == hashlib.sha256(
        f"create_invoice{canonical_json(create_args)}".encode()
    ).hexdigest()

    assert rest_request_for_tool("send_invoice", {"invoice_id": "INV2-ONE"})[:3] == (
        "POST", "https://api-m.sandbox.paypal.com/v2/invoicing/invoices/INV2-ONE/send", {"send_to_invoicer": False}
    )
    assert rest_request_for_tool("get_invoice", {"invoice_id": "INV2-ONE"})[:3] == (
        "GET", "https://api-m.sandbox.paypal.com/v2/invoicing/invoices/INV2-ONE", None
    )
    assert rest_request_for_tool("list_invoices", {})[:3] == (
        "GET", "https://api-m.sandbox.paypal.com/v2/invoicing/invoices?page_size=20", None
    )
    assert rest_request_for_tool("create_refund", {"capture_id": "CAPTURE-1"})[:3] == (
        "POST", "https://api-m.sandbox.paypal.com/v2/payments/captures/CAPTURE-1/refund", None
    )
    assert rest_request_for_tool("create_refund", {"capture_id": "CAPTURE-1", "amount": {"currency_code": "USD", "value": "3.00"}})[2] == {
        "amount": {"currency_code": "USD", "value": "3.00"}
    }


@pytest.mark.parametrize(
    ("tool", "args", "expected_url", "expected_body"),
    [
        ("create_invoice", {"currency_code": "USD", "items": [], "primary_recipients": []}, "/v2/invoicing/invoices", {"detail": {"currency_code": "USD"}, "items": [], "primary_recipients": []}),
        ("send_invoice", {"invoice_id": "INV2-ONE"}, "/v2/invoicing/invoices/INV2-ONE/send", {"send_to_invoicer": False}),
        ("get_invoice", {"invoice_id": "INV2-ONE"}, "/v2/invoicing/invoices/INV2-ONE", None),
        ("list_invoices", {}, "/v2/invoicing/invoices?page_size=20", None),
        ("create_refund", {"capture_id": "CAPTURE-123"}, "/v2/payments/captures/CAPTURE-123/refund", None),
    ],
)
def test_executor_uses_mock_http_transport(tool, args, expected_url, expected_body):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "sandbox-token", "expires_in": 3600, "scope": "invoicing"})
        return httpx.Response(201, json={"id": "PAYPAL-RESULT", "status": "DRAFT"})

    async def execute():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = PayPalTokenProvider("client-id", "client-secret", client=client)
        try:
            return await execute_rest_fallback(tool, args, provider)
        finally:
            await client.aclose()

    result = asyncio.run(execute())
    request = requests[-1]
    assert request.url.host == "api-m.sandbox.paypal.com"
    assert request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "") == expected_url
    if expected_body is not None:
        assert json.loads(request.content) == expected_body
    if request.method == "POST":
        assert request.headers.get("PayPal-Request-Id") == hashlib.sha256(
            f"{tool}{canonical_json(args)}".encode()
        ).hexdigest()
    assert result == {"content": [{"type": "text", "text": '{"id":"PAYPAL-RESULT","status":"DRAFT"}'}], "isError": False}


def test_transport_and_setup_failures_fallback_but_business_422_does_not():
    class Provider:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    class Response:
        status_code = 201

        def json(self):
            return {"id": "INV2-REST"}

    class FallbackProvider(Provider):
        async def request(self, *_args, **_kwargs):
            return Response()

    async def run():
        calls = []
        providers = []

        def factory():
            provider = FallbackProvider()
            providers.append(provider)
            return provider

        async def setup_failure():
            return {"content": [{"type": "text", "text": '{"ok":false,"code":"PAYPAL_API_SETUP_ERROR","message":"Unsupported cache mode: default"}'}], "isError": True}

        setup, transport, mcp_error = await call_with_rest_fallback(
            "create_invoice", {"currency_code": "USD"}, setup_failure, factory, allowed=True
        )
        calls.append((transport, setup))

        async def connection_failure():
            raise TimeoutError("MCP request timed out")

        timeout, timeout_transport, timeout_error = await call_with_rest_fallback(
            "create_invoice", {"currency_code": "USD"}, connection_failure, factory, allowed=True
        )
        calls.append((timeout_transport, timeout))

        async def business_failure():
            return {"content": [{"type": "text", "text": '{"name":"UNPROCESSABLE_ENTITY","details":[{"issue":"MISSING_RECIPIENT_EMAIL"}]}'}], "isError": True}

        business, business_transport, business_error = await call_with_rest_fallback(
            "create_invoice", {}, business_failure, factory, allowed=True
        )
        blocked, blocked_transport, blocked_error = await call_with_rest_fallback(
            "create_invoice", {}, setup_failure, factory, allowed=False
        )
        return calls, providers, (mcp_error, timeout_error, business, business_transport, business_error, blocked, blocked_transport, blocked_error)

    calls, providers, details = asyncio.run(run())
    mcp_error, timeout_error, business, business_transport, business_error, blocked, blocked_transport, blocked_error = details
    assert [transport for transport, _ in calls] == ["rest_fallback", "rest_fallback"]
    assert "PAYPAL_API_SETUP_ERROR" in mcp_error
    assert "TimeoutError" in timeout_error
    assert business_transport == "mcp" and business_error is None
    assert blocked_transport == "mcp" and blocked_error is None
    assert "UNPROCESSABLE_ENTITY" in business["content"][0]["text"]
    assert "PAYPAL_API_SETUP_ERROR" in blocked["content"][0]["text"]
    assert all(provider.closed for provider in providers)


def test_allowed_but_unsupported_tool_stays_on_mcp_transport():
    async def run():
        async def mcp_call():
            return {"content": [{"type": "text", "text": '{"code":"PAYPAL_API_SETUP_ERROR"}'}], "isError": True}

        return await call_with_rest_fallback(
            "generate_invoice_number", {}, mcp_call, lambda: None, allowed=True, enabled=True
        )

    response, transport, mcp_error = asyncio.run(run())
    assert response["isError"] is True
    assert transport == "mcp"
    assert mcp_error is None


def test_recorded_receipt_persists_transport_and_original_mcp_error():
    from paypal_memory import MemoryRepository

    invoices = MemoryRepository()
    obligations = MemoryRepository()
    receipts = MemoryRepository()
    evidence = MemoryRepository()
    passports = MemoryRepository()
    stored = record_tool_result(
        invoices=invoices,
        obligations=obligations,
        receipts=receipts,
        evidence=evidence,
        passports=passports,
        org_id="org-1",
        contract_id="contract-1",
        actor="owner-1",
        tool="list_invoices",
        args={},
        response={"content": [{"type": "text", "text": '{"items":[]}'}], "isError": False},
        decision=GuardDecision("allow", "read-only tool"),
        receipt={"tool": "list_invoices", "transport": "rest_fallback", "mcp_error": "Unsupported cache mode: default"},
        clock=lambda: "2026-10-06T00:00:00Z",
    )
    assert stored["transport"] == "rest_fallback"
    assert stored["mcp_error"] == "Unsupported cache mode: default"


def test_payment_book_server_side_mcp_call_uses_rest_fallback():
    class Provider:
        async def request(self, *_args, **_kwargs):
            class Response:
                status_code = 200

                def json(self):
                    return {"id": "INV2-REST", "status": "DRAFT"}

            return Response()

        async def aclose(self):
            return None

    async def mcp_call(*_args):
        raise httpx.ConnectError("MCP connection refused")

    settings = LexProofSettings(
        paypal_env="sandbox",
        paypal_client_id="client-id",
        paypal_client_secret="client-secret",
    )
    book = PaymentBook(
        settings=settings,
        call_tool=mcp_call,
        rest_provider_factory=Provider,
    )
    response = asyncio.run(book._call_with_fallback(
        "get_invoice",
        {"invoice_id": "INV2-ONE"},
        url="https://mcp.sandbox.paypal.com/sse",
        access_token="sandbox-token",
    ))
    assert response["_lexproof_transport"] == "rest_fallback"
    assert response["_lexproof_mcp_error"].startswith("ConnectError: MCP connection refused")
    assert json.loads(response["content"][0]["text"]) == {"id": "INV2-REST", "status": "DRAFT"}