"""Sandbox REST fallback for the small PayPal MCP tool subset LexProof uses."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .auth import SANDBOX_API_HOST, PayPalTokenProvider
from .receipts import canonical_json

REST_BASE = f"https://{SANDBOX_API_HOST}"
FALLBACK_ENV = "PAYPAL_TRANSPORT_FALLBACK"
_SUPPORTED_TOOLS = frozenset({"create_invoice", "send_invoice", "get_invoice", "list_invoices", "create_refund"})


def supports_rest_fallback(tool: str) -> bool:
    return isinstance(tool, str) and tool.strip().lower() in _SUPPORTED_TOOLS


def fallback_enabled() -> bool:
    """Fallback is on by default only for the configured sandbox environment."""
    mode = os.getenv(FALLBACK_ENV, "rest").strip().lower()
    return mode == "rest" and os.getenv("PAYPAL_ENV", "sandbox").strip().lower() == "sandbox"


def rest_request_for_tool(tool: str, args: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None, dict[str, str]]:
    """Convert one exact MCP argument object into a sandbox REST request."""
    name = tool.strip().lower()
    if name not in _SUPPORTED_TOOLS:
        raise ValueError(f"REST fallback does not support PayPal tool {name}")
    method = "GET"
    body: dict[str, Any] | None = None
    headers: dict[str, str] = {}

    if name == "create_invoice":
        method = "POST"
        detail: dict[str, Any] = {"currency_code": args.get("currency_code")}
        for source, target in (("invoice_number", "invoice_number"), ("invoice_date", "invoice_date"), ("reference", "reference"), ("note", "memo")):
            if source in args:
                detail[target] = args[source]
        body = {"detail": detail}
        if "primary_recipients" in args:
            body["primary_recipients"] = args["primary_recipients"]
        if "items" in args:
            body["items"] = args["items"]
        invoicer: dict[str, Any] = {}
        direct_fields = {
            "business_name": "invoicer_business_name",
            "tax_id": "invoicer_tax_id",
            "email_address": "invoicer_email_address",
        }
        for target, source in direct_fields.items():
            if source in args:
                invoicer[target] = args[source]
        name_fields = {key: args[source] for key, source in (
            ("given_name", "invoicer_given_name"),
            ("surname", "invoicer_surname"),
        ) if source in args}
        if name_fields:
            invoicer["name"] = name_fields
        address_fields = {
            target: args[source]
            for target, source in (
                ("address_line_1", "invoicer_address_line_1"),
                ("address_line_2", "invoicer_address_line_2"),
                ("admin_area_2", "invoicer_city"),
                ("admin_area_1", "invoicer_state"),
                ("postal_code", "invoicer_postal_code"),
                ("country_code", "invoicer_country_code"),
            )
            if source in args
        }
        if address_fields:
            invoicer["address"] = address_fields
        if invoicer:
            body["invoicer"] = invoicer
        headers["Prefer"] = "return=representation"
    elif name == "send_invoice":
        method = "POST"
        invoice_id = _required(args, "invoice_id")
        return method, f"{REST_BASE}/v2/invoicing/invoices/{invoice_id}/send", {"send_to_invoicer": False}, _post_headers(name, args, headers)
    elif name == "get_invoice":
        invoice_id = _required(args, "invoice_id")
        return method, f"{REST_BASE}/v2/invoicing/invoices/{invoice_id}", None, headers
    elif name == "list_invoices":
        return method, f"{REST_BASE}/v2/invoicing/invoices?page_size=20", None, headers
    elif name == "create_refund":
        method = "POST"
        capture_id = _required(args, "capture_id")
        body = {"amount": args["amount"]} if "amount" in args else None
        return method, f"{REST_BASE}/v2/payments/captures/{capture_id}/refund", body, _post_headers(name, args, headers)

    return method, f"{REST_BASE}/v2/invoicing/invoices", body, _post_headers(name, args, headers)


async def execute_rest_fallback(tool: str, args: dict[str, Any], provider: PayPalTokenProvider) -> dict[str, Any]:
    """Execute one sandbox REST operation and return an MCP-shaped result."""
    method, url, body, headers = rest_request_for_tool(tool, args)
    response = await provider.request(method, url, json=body, headers=headers)
    try:
        payload: Any = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = {"message": response.text or f"PayPal returned HTTP {response.status_code}"}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
        "isError": response.status_code >= 400,
    }


async def call_with_rest_fallback(
    tool: str,
    args: dict[str, Any],
    mcp_call: Callable[[], Awaitable[dict[str, Any]]],
    provider_factory: Callable[[], PayPalTokenProvider],
    *,
    allowed: bool,
    enabled: bool | None = None,
    secret: str = "",
) -> tuple[dict[str, Any], str, str | None]:
    """Run MCP once, using REST only after an allowed call's transport/setup failure."""
    try:
        result = await mcp_call()
    except Exception as exc:
        if not allowed or not supports_rest_fallback(tool) or not (fallback_enabled() if enabled is None else enabled) or not is_transport_exception(exc):
            raise
        mcp_error = _scrub(_error_text(exc), secret)
    else:
        mcp_error = setup_failure_text(result)
        if not allowed or not supports_rest_fallback(tool) or not mcp_error or not (fallback_enabled() if enabled is None else enabled):
            return result, "mcp", None
        mcp_error = _scrub(mcp_error, secret)

    provider = provider_factory()
    try:
        return await execute_rest_fallback(tool, args, provider), "rest_fallback", mcp_error
    finally:
        await provider.aclose()


def setup_failure_text(result: Any) -> str | None:
    """Return the original setup-failure text, but never classify PayPal 4xx as transport."""
    for text in _text_blocks(result):
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("code") == "PAYPAL_API_SETUP_ERROR":
            return text
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, str) and _is_transport_message(error):
            return error
        if result.get("isError"):
            texts = _text_blocks(result)
            if not any(_is_paypal_business_error(text) for text in texts):
                # MCP-layer failure (tool wrapper error, not a PayPal API answer):
                # safe to replay the same, already-allowed call over REST.
                return " | ".join(texts)[:600] or "MCP tool returned isError without a PayPal error body"
    return None


_PAYPAL_BUSINESS_NAMES = {
    "UNPROCESSABLE_ENTITY",
    "INVALID_REQUEST",
    "RESOURCE_NOT_FOUND",
    "NOT_AUTHORIZED",
    "PERMISSION_DENIED",
    "VALIDATION_ERROR",
    "DUPLICATE_REQUEST_ID",
}


def _is_paypal_business_error(text: str) -> bool:
    """True when the text is a real PayPal API error answer (must not be replayed)."""
    lowered = text.lower()
    if any(term in lowered for term in ("unprocessable_entity", "validation_error", "missing_recipient_email")):
        return True
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if str(payload.get("name") or "").upper() in _PAYPAL_BUSINESS_NAMES:
        return True
    details = payload.get("details")
    return isinstance(details, list) and any(isinstance(item, dict) and item.get("issue") for item in details)


def is_transport_exception(error: BaseException) -> bool:
    """Recognize connection/timeout failures and ADK's wrapped transport errors."""
    if isinstance(error, (TimeoutError, asyncio.TimeoutError, httpx.TransportError, ConnectionError)):
        return True
    return _is_transport_message(_error_text(error))


def _is_transport_message(message: str) -> bool:
    lowered = message.lower()
    if any(term in lowered for term in ("unprocessable_entity", "validation_error", "missing_recipient_email")):
        return False
    return any(term in lowered for term in (
        "connectionerror", "connection error", "connection reset", "connection refused",
        "connecterror", "connect error", "timeout", "timed out", "readerror", "read error",
        "transport error", "transport closed", "stream closed", "mcp tool execution failed",
        "502 bad gateway", "503 service unavailable", "504 gateway timeout",
    ))


def _text_blocks(value: Any) -> list[str]:
    if isinstance(value, dict):
        found: list[str] = []
        for block in value.get("content") or []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                found.append(block["text"])
        return found
    return []


def _post_headers(tool: str, args: dict[str, Any], headers: dict[str, str]) -> dict[str, str]:
    request_id = hashlib.sha256(f"{tool.strip().lower()}{canonical_json(args)}".encode("utf-8")).hexdigest()
    return {**headers, "PayPal-Request-Id": request_id}


def _required(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"REST fallback requires {key}")
    return value.strip()


def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:1000]


def _scrub(text: str, secret: str) -> str:
    return text.replace(secret, "[redacted]") if secret else text