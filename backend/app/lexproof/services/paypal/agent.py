"""Sandbox PayPal agent backed by Google ADK and PayPal's hosted MCP server.

The 2026-10-05 sandbox probe answered ``tools/list`` on SSE at
``https://mcp.sandbox.paypal.com/sse``. Streamable HTTP (``/http``) was not
required. Transport detection still tries the URL's path first, then the other
sandbox path when the mode is ``auto``. ``PAYPAL_MCP_TRANSPORT=stdio`` switches
to ``npx -y @paypal/mcp --tools=all`` with ``PAYPAL_ENVIRONMENT=SANDBOX``.
Live PayPal hosts are rejected.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .guard import ApprovedObligation, GuardDecision, decide
from .receipts import canonical_receipt

SANDBOX_MCP_HOST = "mcp.sandbox.paypal.com"
SANDBOX_MCP_ORIGIN = "https://mcp.sandbox.paypal.com"
TRANSPORT_ENV = "PAYPAL_MCP_TRANSPORT"

_AGENT_INSTRUCTION = (
    "You are LexProof's sandbox PayPal assistant. "
    "When the user asks about invoices, call list_invoices. "
    "When the user asks for a refund, call create_refund immediately with the "
    "invoice id they gave. Do not look the invoice up first and do not refuse "
    "before that tool returns. "
    "Pass tool results through. Do not invent a payment result when a tool returns blocked."
)


@dataclass
class PayPalAgentGuard:
    """Closes over the mandate and records every guard decision for the caller."""

    mandate: list[ApprovedObligation]
    approvals: set[str]
    actor: str
    contract_id: str
    invoice_ledger: dict[str, Any] = field(default_factory=dict)
    result_hook: Any = None
    decisions: list[GuardDecision] = field(default_factory=list)
    calls: list[tuple[str, GuardDecision]] = field(default_factory=list)
    receipts: list[dict[str, Any]] = field(default_factory=list)

    async def before_tool(self, tool: Any, args: Any, tool_context: Any) -> dict[str, Any] | None:
        name = _tool_name(tool)
        decision = decide(name, args, self.mandate, self.approvals, self.invoice_ledger)
        self.decisions.append(decision)
        self.calls.append((name, decision))
        if decision.decision == "allow":
            return None
        return {
            "blocked": True,
            "decision": decision.decision,
            "reason": decision.reason,
            "matched_obligation_id": decision.matched_obligation_id,
        }

    async def after_tool(
        self,
        tool: Any,
        args: Any,
        tool_context: Any,
        tool_response: dict[str, Any],
    ) -> dict[str, Any]:
        name = _tool_name(tool)
        decision = self.decisions[-1] if self.decisions else decide(name, args, self.mandate, self.approvals, self.invoice_ledger)
        payload = args if isinstance(args, dict) else {}
        receipt = canonical_receipt(name, payload, tool_response, decision, self.actor, self.contract_id)
        self.receipts.append(receipt)
        if self.result_hook is not None:
            await self.result_hook(name, payload, tool_response, decision, receipt)
        return receipt


def assert_sandbox_mcp_url(url: str) -> None:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or parsed.scheme != "https" or host != SANDBOX_MCP_HOST:
        raise RuntimeError("PayPal MCP URL must be https://mcp.sandbox.paypal.com with no embedded credentials")


def transport_for_url(url: str) -> str:
    """Return ``sse`` or ``http`` from the sandbox MCP path."""
    assert_sandbox_mcp_url(url)
    path = urlparse(url.strip()).path.rstrip("/").lower()
    if path.endswith("/http"):
        return "http"
    if path.endswith("/sse"):
        return "sse"
    raise RuntimeError("PayPal MCP URL path must end in /sse or /http")


def alternate_mcp_url(url: str) -> str:
    if transport_for_url(url) == "sse":
        return f"{SANDBOX_MCP_ORIGIN}/http"
    return f"{SANDBOX_MCP_ORIGIN}/sse"


def resolve_transport_mode(explicit: str | None = None) -> str:
    mode = (explicit if explicit is not None else os.getenv(TRANSPORT_ENV, "auto")).strip().lower()
    if mode not in {"auto", "sse", "http", "stdio"}:
        raise RuntimeError("PAYPAL_MCP_TRANSPORT must be auto, sse, http, or stdio")
    return mode


def build_stdio_server_params(access_token: str) -> Any:
    """Local MCP server. Sandbox only, and the client secret is not forwarded.

    ``mcp`` takes about two seconds to import. It stays inside this function
    so application startup, including /health, does not pay that cost.
    """
    from mcp import StdioServerParameters

    if not access_token:
        raise RuntimeError("PayPal stdio MCP requires an access token")
    env = dict(os.environ)
    env["PAYPAL_ACCESS_TOKEN"] = access_token
    env["PAYPAL_ENVIRONMENT"] = "SANDBOX"
    env.pop("PAYPAL_CLIENT_SECRET", None)
    return StdioServerParameters(
        command="npx",
        args=["-y", "@paypal/mcp", "--tools=all"],
        env=env,
    )


def build_mcp_toolset(url: str, access_token: str, transport: str) -> Any:
    """Build an ADK toolset. Does not open the connection until the agent runs."""
    from google.adk.tools.mcp_tool.mcp_session_manager import (
        SseConnectionParams,
        StdioConnectionParams,
        StreamableHTTPConnectionParams,
    )
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

    if transport == "stdio":
        return McpToolset(
            connection_params=StdioConnectionParams(
                server_params=build_stdio_server_params(access_token),
                timeout=60,
            )
        )
    assert_sandbox_mcp_url(url)
    headers = {"Authorization": f"Bearer {access_token}"}
    if transport == "sse":
        params: Any = SseConnectionParams(url=url, headers=headers, timeout=30, sse_read_timeout=60)
    elif transport == "http":
        params = StreamableHTTPConnectionParams(url=url, headers=headers, timeout=30, sse_read_timeout=60)
    else:
        raise RuntimeError("PayPal MCP transport must be sse, http, or stdio")
    return McpToolset(connection_params=params)


def use_vertex_ai() -> None:
    """Route ADK's Gemini calls through Vertex AI with the service account (ADC).

    google-genai defaults to the Gemini Developer API, which needs an API key;
    on Cloud Run that failed with "No API key was provided". LexProof already
    uses Vertex AI (GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION), so opt in
    unless the environment says otherwise.
    """
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")


def build_paypal_agent(
    *,
    model: str,
    mcp_url: str,
    access_token: str,
    transport: str,
    guard: PayPalAgentGuard,
    toolset: Any | None = None,
) -> Any:
    """ADK agent whose tools are the PayPal MCP server, guarded before each call."""
    from google.adk.agents import Agent

    use_vertex_ai()

    selected = toolset if toolset is not None else build_mcp_toolset(mcp_url, access_token, transport)
    return Agent(
        name="lexproof_paypal",
        model=model,
        description="Sandbox PayPal assistant guarded by LexProof PaymentGuard.",
        instruction=_AGENT_INSTRUCTION,
        tools=[selected],
        before_tool_callback=guard.before_tool,
        after_tool_callback=guard.after_tool,
    )


async def probe_paypal_mcp(
    url: str,
    access_token: str,
    *,
    mode: str | None = None,
) -> tuple[str, str, list[str]]:
    """Connect and list tool names. Returns ``(transport, url, names)``."""
    selected = resolve_transport_mode(mode)
    if selected == "stdio":
        names = await _list_stdio(access_token)
        return "stdio", "npx:-y:@paypal/mcp", names

    candidates = _candidates(url, selected)
    errors: list[str] = []
    for transport, candidate in candidates:
        try:
            names = await asyncio.wait_for(_list_remote(candidate, access_token, transport), timeout=45)
            return transport, candidate, names
        except Exception as exc:
            errors.append(f"{transport} {candidate}: {_public_error(exc, access_token)}")
    joined = "; ".join(errors)
    raise RuntimeError(f"PayPal sandbox MCP probe failed: {joined}")


async def call_paypal_tool(url: str, access_token: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call one stored tool on the sandbox MCP server. Does not ask the model."""
    assert_sandbox_mcp_url(url)
    kind = transport_for_url(url)
    if kind == "sse":
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        headers = {"Authorization": f"Bearer {access_token}"}
        async with sse_client(url, headers=headers, timeout=30, sse_read_timeout=60) as (read, write):
            return await _call_session(read, write, tool_name, arguments)
    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json, text/event-stream"}
    timeout = httpx2.Timeout(30.0, read=60.0)
    async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            return await _call_session(read, write, tool_name, arguments)


async def run_paypal_turn(
    *,
    model: str,
    mcp_url: str,
    access_token: str,
    transport: str,
    guard: PayPalAgentGuard,
    message: str,
    user_id: str,
    session_id: str | None = None,
    timeout_seconds: float = 60,
) -> dict[str, str]:
    """One guarded agent turn. The MCP toolset is closed when the turn ends."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    toolset = build_mcp_toolset(mcp_url, access_token, transport)
    agent = build_paypal_agent(
        model=model,
        mcp_url=mcp_url,
        access_token=access_token,
        transport=transport,
        guard=guard,
        toolset=toolset,
    )
    sessions = _session_service()
    if not isinstance(sessions, InMemorySessionService):
        sessions = InMemorySessionService()
    if session_id:
        session = await sessions.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        if session is None:
            session = await sessions.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    else:
        session = await sessions.create_session(app_name=APP_NAME, user_id=user_id)
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=sessions)

    async def _run() -> str:
        parts: list[str] = []
        content = types.Content(role="user", parts=[types.Part(text=message)])
        async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=content):
            text = _event_text(event)
            if text:
                parts.append(text)
        return "\n".join(parts)

    try:
        text = await asyncio.wait_for(_run(), timeout=timeout_seconds)
    finally:
        close = getattr(toolset, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
    return {"session_id": session.id, "text": text}


APP_NAME = "lexproof-paypal"
_SESSIONS: Any = None


def _session_service() -> Any:
    global _SESSIONS
    if _SESSIONS is None:
        from google.adk.sessions import InMemorySessionService

        _SESSIONS = InMemorySessionService()
    return _SESSIONS


async def _call_session(read: Any, write: Any, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mcp import ClientSession

    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)
    return _mcp_result(result)


def _mcp_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    content: list[dict[str, Any]] = []
    for block in getattr(result, "content", ()) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            content.append({"type": "text", "text": text})
    return {"content": content, "isError": bool(getattr(result, "isError", False))}


def _event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    lines: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            lines.append(str(text))
    return "\n".join(lines)


def scrub_secret(text: str, secret: str) -> str:
    if secret:
        return text.replace(secret, "[redacted]")
    return text


async def _list_remote(url: str, access_token: str, transport: str) -> list[str]:
    assert_sandbox_mcp_url(url)
    if transport == "sse":
        return await _list_sse(url, access_token)
    if transport == "http":
        return await _list_http(url, access_token)
    raise RuntimeError("PayPal MCP transport must be sse or http")


def _candidates(url: str, mode: str) -> list[tuple[str, str]]:
    if mode == "sse":
        return [("sse", f"{SANDBOX_MCP_ORIGIN}/sse")]
    if mode == "http":
        return [("http", f"{SANDBOX_MCP_ORIGIN}/http")]
    primary = transport_for_url(url)
    ordered = [(primary, url.strip())]
    alternate = alternate_mcp_url(url)
    ordered.append((transport_for_url(alternate), alternate))
    return ordered


async def _list_sse(url: str, access_token: str) -> list[str]:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    headers = {"Authorization": f"Bearer {access_token}"}
    async with sse_client(url, headers=headers, timeout=30, sse_read_timeout=60) as (read, write):
        return await _tool_names(read, write)


async def _list_http(url: str, access_token: str) -> list[str]:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json, text/event-stream",
    }
    timeout = httpx2.Timeout(30.0, read=60.0)
    async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            return await _tool_names(read, write)


async def _list_stdio(access_token: str) -> list[str]:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(build_stdio_server_params(access_token)) as (read, write):
        return await _tool_names(read, write)


async def _tool_names(read: Any, write: Any) -> list[str]:
    from mcp import ClientSession

    async with ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
    tools = getattr(listed, "tools", ())
    names: list[str] = []
    for tool in tools:
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    return str(tool)


def _public_error(exc: BaseException, secret: str) -> str:
    text = scrub_secret(f"{type(exc).__name__}: {exc}", secret)
    return text[:500]
