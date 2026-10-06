"""List sandbox PayPal MCP tools and show the payment guard blocking a refund.

Does not call live PayPal hosts. Prints tool names and guard decisions.
Access tokens are not printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.services.paypal.agent import (
    PayPalAgentGuard,
    build_paypal_agent,
    probe_paypal_mcp,
    scrub_secret,
)
from app.lexproof.services.paypal.auth import PayPalTokenProvider, log_invoicing_scope
from app.lexproof.services.paypal.guard import ToolClass, classify


APP_NAME = "lexproof-paypal-spike"
USER_ID = "paypal-spike"


async def _ask(runner: object, session_service: object, prompt: str, guard: PayPalAgentGuard, secret: str) -> None:
    from google.genai import types

    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    print(f"prompt: {prompt}")
    before = len(guard.decisions)
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=content):
        summary = scrub_secret(_event_summary(event), secret)
        if summary:
            print(summary)
    print("guard_decisions:")
    fresh = guard.decisions[before:]
    if not fresh:
        print("  (no tool call)")
    for decision in fresh:
        print(f"  {decision.decision}: {decision.reason}")


def _event_summary(event: object) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    lines: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            lines.append(text)
        call = getattr(part, "function_call", None)
        if call is not None:
            lines.append(f"tool_call {getattr(call, 'name', '')}")
        response = getattr(part, "function_response", None)
        if response is not None:
            lines.append(f"tool_response {getattr(response, 'name', '')}: {getattr(response, 'response', '')}")
    return "\n".join(lines)


SCHEMA_TOOLS = (
    "create_invoice",
    "send_invoice",
    "send_invoice_reminder",
    "create_refund",
    "get_invoice",
    "create_order",
)


async def _print_schemas(url: str, token: str, wanted: set[str]) -> None:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    headers = {"Authorization": f"Bearer {token}"}
    async with sse_client(url, headers=headers, timeout=30, sse_read_timeout=60) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    found = {getattr(tool, "name", ""): tool for tool in getattr(listed, "tools", ())}
    missing = sorted(wanted - set(found))
    if missing:
        raise SystemExit("schema not found for: " + ", ".join(missing))
    for name in sorted(wanted):
        tool = found[name]
        raw = tool.model_dump() if hasattr(tool, "model_dump") else {"repr": repr(tool)}
        schema = raw.get("inputSchema") or raw.get("input_schema")
        print(f"SCHEMA {name}")
        print(json.dumps(schema, indent=2, default=str))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schema",
        nargs="*",
        default=None,
        help="Print inputSchema for these tools and exit. With no names, dumps the invoice tools.",
    )
    args = parser.parse_args()
    settings = get_settings()
    if not settings.has_paypal_configuration():
        raise SystemExit("PayPal is not configured")
    if settings.paypal_env.strip().lower() != "sandbox":
        raise SystemExit("PayPal integration is sandbox-only")

    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    if settings.project_id:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.project_id)
    if settings.google_cloud_location:
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location)

    provider = PayPalTokenProvider(
        settings.paypal_client_id,
        settings.paypal_client_secret.get_secret_value(),
    )
    try:
        token = await provider.get_access_token()
        present = log_invoicing_scope(provider.scopes)
        print(f"invoicing_scope_present={present}")
        transport, url, names = await probe_paypal_mcp(settings.paypal_mcp_url, token)
        if args.schema is not None:
            wanted = set(args.schema) or set(SCHEMA_TOOLS)
            await _print_schemas(url if transport != "stdio" else "https://mcp.sandbox.paypal.com/sse", token, wanted)
            return
        print(f"mcp_transport={transport}")
        print(f"mcp_url={url}")
        print("tools:")
        for name in names:
            print(f"  {name}")

        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        guard = PayPalAgentGuard(mandate=[], approvals=set(), actor="paypal-spike", contract_id="spike")
        agent = build_paypal_agent(
            model=settings.gemini_model,
            mcp_url=url if transport != "stdio" else settings.paypal_mcp_url,
            access_token=token,
            transport=transport,
            guard=guard,
        )
        session_service = InMemorySessionService()
        runner = Runner(app_name=APP_NAME, agent=agent, session_service=session_service)
        await _ask(runner, session_service, "list my recent invoices", guard, token)
        await _ask(runner, session_service, "refund invoice X", guard, token)
        blocked = [
            decision
            for name, decision in guard.calls
            if classify(name) is ToolClass.MONEY_OUT and decision.decision != "allow"
        ]
        if not blocked:
            raise SystemExit("refund was not blocked by the payment guard")
    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
