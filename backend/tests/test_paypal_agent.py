"""PayPal settings, startup probe, and agent guard wiring. No live network."""

import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.lexproof.config import LexProofSettings
from app.lexproof.services.paypal.agent import (
    PayPalAgentGuard,
    alternate_mcp_url,
    assert_sandbox_mcp_url,
    build_mcp_toolset,
    build_paypal_agent,
    build_stdio_server_params,
    probe_paypal_mcp,
    resolve_transport_mode,
    transport_for_url,
)
from app.lexproof.services.paypal.startup import run_paypal_startup


def _sandbox(**overrides) -> LexProofSettings:
    values = {
        "paypal_env": "sandbox",
        "paypal_client_id": "client-id",
        "paypal_client_secret": "client-secret",
        "paypal_mcp_url": "https://mcp.sandbox.paypal.com/sse",
    }
    values.update(overrides)
    return LexProofSettings(**values)


def test_paypal_settings_follow_env_names_and_hide_the_secret():
    settings = _sandbox(paypal_webhook_id="wh-1")
    assert settings.paypal_env == "sandbox"
    assert settings.paypal_webhook_id == "wh-1"
    assert settings.has_paypal_configuration() is True
    assert "client-secret" not in repr(settings)

    disabled = LexProofSettings(paypal_env="live", paypal_client_id="", paypal_client_secret="")
    assert disabled.has_paypal_configuration() is False
    assert disabled.paypal_env == "live"


def test_configured_live_paypal_and_non_sandbox_urls_are_rejected():
    with pytest.raises(ValidationError):
        _sandbox(paypal_env="live")
    with pytest.raises(ValidationError):
        _sandbox(paypal_mcp_url="https://mcp.paypal.com/sse")
    with pytest.raises(ValidationError):
        _sandbox(paypal_mcp_url="https://user:secret@mcp.sandbox.paypal.com/sse")
    with pytest.raises(ValidationError):
        _sandbox(paypal_mcp_url="http://mcp.sandbox.paypal.com/sse")


@pytest.mark.asyncio
async def test_startup_skips_the_network_probe_under_pytest(monkeypatch):
    created = []

    class FakeProvider:
        def __init__(self, client_id, client_secret):
            created.append(client_secret)

        async def get_access_token(self):
            return "sandbox-token"

        async def aclose(self):
            return None

    monkeypatch.setattr("app.lexproof.services.paypal.startup.PayPalTokenProvider", FakeProvider)
    await run_paypal_startup(_sandbox())
    assert created == []


@pytest.mark.asyncio
async def test_startup_probe_logs_invoicing_without_the_token(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    class FakeProvider:
        def __init__(self, client_id, client_secret):
            assert client_secret == "client-secret"
            self.scopes = ("https://uri.paypal.com/services/invoicing",)
            self.closed = False

        async def get_access_token(self):
            return "sandbox-token-value"

        async def aclose(self):
            self.closed = True

    holder = {}

    class Capturing(FakeProvider):
        def __init__(self, client_id, client_secret):
            super().__init__(client_id, client_secret)
            holder["provider"] = self

    monkeypatch.setattr("app.lexproof.services.paypal.startup.PayPalTokenProvider", Capturing)
    await run_paypal_startup(_sandbox(), probe=True)
    assert holder["provider"].closed is True
    assert "PayPal invoicing scope present: True" in caplog.text
    assert "sandbox-token-value" not in caplog.text
    assert "client-secret" not in caplog.text


@pytest.mark.asyncio
async def test_startup_rejects_a_mutated_live_environment_before_the_network():
    settings = _sandbox()
    settings.paypal_env = "live"
    with pytest.raises(RuntimeError, match="sandbox-only"):
        await run_paypal_startup(settings, probe=True)


@pytest.mark.asyncio
async def test_startup_returns_when_paypal_is_not_configured():
    await run_paypal_startup(LexProofSettings(paypal_client_id="", paypal_client_secret=""))


def test_transport_detection_stays_on_the_sandbox_host(monkeypatch):
    assert transport_for_url("https://mcp.sandbox.paypal.com/sse") == "sse"
    assert transport_for_url("https://mcp.sandbox.paypal.com/http") == "http"
    assert alternate_mcp_url("https://mcp.sandbox.paypal.com/sse") == "https://mcp.sandbox.paypal.com/http"
    assert alternate_mcp_url("https://mcp.sandbox.paypal.com/http") == "https://mcp.sandbox.paypal.com/sse"
    with pytest.raises(RuntimeError):
        assert_sandbox_mcp_url("https://mcp.paypal.com/sse")
    with pytest.raises(RuntimeError):
        transport_for_url("https://mcp.sandbox.paypal.com/mcp")
    monkeypatch.setenv("PAYPAL_MCP_TRANSPORT", "stdio")
    assert resolve_transport_mode() == "stdio"
    assert resolve_transport_mode("http") == "http"
    monkeypatch.setenv("PAYPAL_MCP_TRANSPORT", "nope")
    with pytest.raises(RuntimeError):
        resolve_transport_mode()


def test_stdio_fallback_is_sandbox_and_does_not_forward_the_client_secret(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "super-secret")
    with pytest.raises(RuntimeError):
        build_stdio_server_params("")
    params = build_stdio_server_params("sandbox-token")
    assert params.command == "npx"
    assert params.args == ["-y", "@paypal/mcp", "--tools=all"]
    assert params.env["PAYPAL_ENVIRONMENT"] == "SANDBOX"
    assert params.env["PAYPAL_ACCESS_TOKEN"] == "sandbox-token"
    assert "PAYPAL_CLIENT_SECRET" not in params.env
    assert os_has_secret()


def os_has_secret():
    import os

    return os.environ.get("PAYPAL_CLIENT_SECRET") == "super-secret"


def test_mcp_toolset_rejects_live_and_builds_sandbox_connections():
    with pytest.raises(RuntimeError):
        build_mcp_toolset("https://mcp.paypal.com/sse", "sandbox-token", "sse")
    sse_toolset = build_mcp_toolset("https://mcp.sandbox.paypal.com/sse", "sandbox-token", "sse")
    http_toolset = build_mcp_toolset("https://mcp.sandbox.paypal.com/http", "sandbox-token", "http")
    stdio_toolset = build_mcp_toolset("https://mcp.sandbox.paypal.com/sse", "sandbox-token", "stdio")
    assert sse_toolset is not None
    assert http_toolset is not None
    assert stdio_toolset is not None
    with pytest.raises(RuntimeError):
        build_mcp_toolset("https://mcp.sandbox.paypal.com/sse", "sandbox-token", "websocket")


@pytest.mark.asyncio
async def test_guard_callbacks_block_refunds_and_return_a_receipt():
    guard = PayPalAgentGuard(mandate=[], approvals=set(), actor="actor@example.com", contract_id="contract-1")
    tool = SimpleNamespace(name="list_invoices")
    assert await guard.before_tool(tool, {}, None) is None
    receipt = await guard.after_tool(tool, {}, None, {"items": [], "access_token": "sandbox-token"})
    assert receipt["decision"] == "allow"
    assert "access_token" not in receipt["response"]
    assert guard.receipts == [receipt]

    refund = SimpleNamespace(name="create_refund")
    blocked = await guard.before_tool(refund, {"invoice_id": "X"}, None)
    assert blocked["blocked"] is True
    assert blocked["decision"] == "needs_approval"
    wrapped = await guard.after_tool(refund, {"invoice_id": "X"}, None, blocked)
    assert wrapped["response"]["blocked"] is True
    assert wrapped["decision"] == "needs_approval"
    assert len(guard.decisions) == 2


@pytest.mark.asyncio
async def test_probe_falls_back_from_sse_to_http_and_scrubs_the_token(monkeypatch):
    token = "sandbox-token-value"
    calls = []

    async def fake_list(url, access_token, transport):
        calls.append((transport, url))
        if transport == "sse":
            raise RuntimeError(f"connect failed bearer {access_token}")
        return ["list_invoices", "create_refund"]

    monkeypatch.setattr("app.lexproof.services.paypal.agent._list_remote", fake_list)
    transport, url, names = await probe_paypal_mcp("https://mcp.sandbox.paypal.com/sse", token, mode="auto")
    assert transport == "http"
    assert url == "https://mcp.sandbox.paypal.com/http"
    assert names == ["list_invoices", "create_refund"]
    assert calls[0][0] == "sse"

    async def always_fail(url, access_token, transport):
        raise RuntimeError(f"header {access_token}")

    monkeypatch.setattr("app.lexproof.services.paypal.agent._list_remote", always_fail)
    with pytest.raises(RuntimeError) as exc:
        await probe_paypal_mcp("https://mcp.sandbox.paypal.com/sse", token, mode="sse")
    assert token not in str(exc.value)
    assert "[redacted]" in str(exc.value)


def test_agent_uses_the_configured_model_and_callbacks():
    guard = PayPalAgentGuard(mandate=[], approvals=set(), actor="actor", contract_id="c-1")
    toolset = build_mcp_toolset("https://mcp.sandbox.paypal.com/sse", "sandbox-token", "sse")
    agent = build_paypal_agent(
        model="gemini-2.0-flash-001",
        mcp_url="https://mcp.sandbox.paypal.com/sse",
        access_token="sandbox-token",
        transport="sse",
        guard=guard,
        toolset=toolset,
    )
    assert agent.model == "gemini-2.0-flash-001"
    assert agent.before_tool_callback == guard.before_tool
    assert agent.after_tool_callback == guard.after_tool
    assert agent.tools == [toolset]
