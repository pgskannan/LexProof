from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.lexproof.api import voice as voice_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services import firebase_auth
from app.lexproof.services.voice_assistant import VoiceAssistantService, VoiceSessionStore


class ScriptedExecutor:
    def __init__(self, scripts: dict[str, list[tuple[str, dict[str, Any], Any]]] | None = None):
        self.scripts = scripts or {}
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *, utterance, uid, session_id, authorization, org_id, guard):
        self.calls.append({
            "utterance": utterance,
            "uid": uid,
            "session_id": session_id,
            "authorization": authorization,
            "org_id": org_id,
        })
        for index, (tool_name, arguments, output) in enumerate(self.scripts.get(utterance, [])):
            tool = SimpleNamespace(name=tool_name)
            context = SimpleNamespace(function_call_id=f"{session_id}-{index}")
            blocked = await guard.before_tool(tool, arguments, context)
            if blocked is None:
                await guard.after_tool(tool, arguments, context, output)
        return {"display_text": f"I heard: {utterance}", "speech": "I heard you."}


def _prepared_output(code: str = "AB12CD") -> dict[str, Any]:
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    return {
        "structuredContent": {
            "summary": "Approve the annual license payment",
            "confirmation_code": code,
            "confirmation_token": "signed.full-secret-token-value",
            "expires_at": expiry,
            "speech": f"Ready to approve. Say confirm {code} to proceed.",
        }
    }


def _app(monkeypatch, executor: ScriptedExecutor, *, uid: str = "user-a"):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    monkeypatch.setattr(
        voice_api,
        "_assistant",
        VoiceAssistantService(sessions=VoiceSessionStore(), agent_executor=executor),
    )
    return TestClient(app)


def _turn(client: TestClient, utterance: str, *, session_id: str | None = None, org_id: str = "org-a"):
    body: dict[str, Any] = {"utterance": utterance}
    if session_id:
        body["session_id"] = session_id
    return client.post(
        "/api/voice/turn",
        headers={"Authorization": "Bearer test-user-token", "X-Org-Id": org_id},
        json=body,
    )


@pytest.mark.parametrize("utterance", ["confirm", "yes"])
def test_prepared_decision_can_be_confirmed_in_next_turn(monkeypatch, utterance):
    executor = ScriptedExecutor({
        "prepare": [("prepare_decision", {}, _prepared_output())],
        utterance: [("confirm_decision", {"confirmation_code": "AB12CD"}, {"speech": "Approved."})],
    })
    client = _app(monkeypatch, executor)

    prepared = _turn(client, "prepare").json()
    confirmed = _turn(client, utterance, session_id=prepared["session_id"])

    assert confirmed.status_code == 200
    assert confirmed.json()["tool_trace"][0]["ok"] is True
    assert confirmed.json()["awaiting_confirmation"] is None


def test_confirm_without_prepare_is_blocked(monkeypatch):
    executor = ScriptedExecutor({
        "confirm": [("confirm_decision", {"confirmation_code": "AB12CD"}, {"success": True})],
    })
    response = _turn(_app(monkeypatch, executor), "confirm")

    assert response.status_code == 200
    assert response.json()["speech"] == "I need you to say 'confirm' first. Nothing has changed."
    assert response.json()["tool_trace"][0]["ok"] is False


def test_prepare_and_confirm_in_same_turn_is_blocked(monkeypatch):
    executor = ScriptedExecutor({
        "approve it": [
            ("prepare_decision", {}, _prepared_output()),
            ("confirm_decision", {"confirmation_code": "AB12CD"}, {"success": True}),
        ],
    })
    response = _turn(_app(monkeypatch, executor), "approve it")

    assert response.status_code == 200
    assert response.json()["speech"] == "I need you to say 'confirm' first. Nothing has changed."
    assert response.json()["tool_trace"][0]["ok"] is True
    assert response.json()["tool_trace"][1]["ok"] is False


def test_prepare_becomes_stale_after_an_intervening_turn(monkeypatch):
    executor = ScriptedExecutor({
        "prepare": [("prepare_decision", {}, _prepared_output())],
        "confirm": [("confirm_decision", {"confirmation_code": "AB12CD"}, {"success": True})],
    })
    client = _app(monkeypatch, executor)
    prepared = _turn(client, "prepare").json()
    _turn(client, "continue", session_id=prepared["session_id"])
    response = _turn(client, "confirm", session_id=prepared["session_id"])

    assert response.status_code == 200
    assert response.json()["speech"] == "I need you to say 'confirm' first. Nothing has changed."


def test_wrong_confirmation_code_is_blocked(monkeypatch):
    executor = ScriptedExecutor({
        "prepare": [("prepare_decision", {}, _prepared_output())],
        "confirm WRONG99": [("confirm_decision", {"confirmation_code": "WRONG99"}, {"success": True})],
    })
    client = _app(monkeypatch, executor)
    prepared = _turn(client, "prepare").json()
    response = _turn(client, "confirm WRONG99", session_id=prepared["session_id"])

    assert response.status_code == 200
    assert response.json()["speech"] == "I need you to say 'confirm' first. Nothing has changed."
    assert response.json()["tool_trace"][0]["ok"] is False


def test_judge_can_post_and_is_rate_limited(monkeypatch):
    executor = ScriptedExecutor()
    client = _app(monkeypatch, executor, uid="judge-a")
    monkeypatch.setattr(voice_api.get_settings(), "judge_can_analyze", True)
    monkeypatch.setattr(voice_api, "read_only_uids", lambda: {"judge-a"})
    hits = 0

    def limiter(uid: str):
        nonlocal hits
        hits += 1
        if hits > 1:
            raise HTTPException(status_code=429, detail="Judge turn limit reached")

    monkeypatch.setattr(voice_api, "check_judge_interaction_rate", limiter)

    first = _turn(client, "hello")
    second = _turn(client, "again")

    assert first.status_code == 200
    assert second.status_code == 429
    assert hits == 2


def test_tool_trace_redacts_bearer_and_full_confirmation_token(monkeypatch):
    token = "A" * 48 + "." + "B" * 48
    prepared_output = _prepared_output()
    prepared_output["structuredContent"]["speech"] = f"Bearer test-user-token {token}"
    executor = ScriptedExecutor({
        "inspect": [(
            "prepare_decision",
            {"authorization": "Bearer test-user-token", "confirmation_token": token},
            prepared_output,
        )],
    })
    client = _app(monkeypatch, executor)
    body = _turn(client, "inspect").json()
    serialized = json.dumps(body)

    assert "test-user-token" not in serialized
    assert token not in serialized
    assert "[redacted]" in body["tool_trace"][0]["arguments_summary"]
    assert "Bearer [redacted]" in body["speech"]


def test_session_id_cannot_be_used_by_another_user(monkeypatch):
    executor = ScriptedExecutor()
    client = _app(monkeypatch, executor)
    created = _turn(client, "hello").json()
    app = client.app
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-b"}

    response = _turn(client, "hello", session_id=created["session_id"])

    assert response.status_code == 404


def test_turn_forwards_raw_bearer_and_org_header(monkeypatch):
    executor = ScriptedExecutor()
    client = _app(monkeypatch, executor)
    response = _turn(client, "hello", org_id="org-forwarded")

    assert response.status_code == 200
    assert executor.calls[0]["authorization"] == "Bearer test-user-token"
    assert executor.calls[0]["org_id"] == "org-forwarded"


def test_timeout_returns_sanitized_504_speech(monkeypatch):
    async def slow_executor(**kwargs):
        await asyncio.sleep(1)
        return {"speech": "late"}

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-a"}
    monkeypatch.setattr(
        voice_api,
        "_assistant",
        VoiceAssistantService(agent_executor=slow_executor, timeout_seconds=0.01),
    )

    response = _turn(TestClient(app), "hello")

    assert response.status_code == 504
    assert response.json()["speech"] == "That took too long. Please try again."
    assert response.json()["session_id"]


class MCPConnectionFailure(ConnectionError):
    pass


def test_mcp_connection_failure_returns_sanitized_502(monkeypatch):
    async def failing_executor(**kwargs):
        raise MCPConnectionFailure("failed with secret token")

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-a"}
    monkeypatch.setattr(voice_api, "_assistant", VoiceAssistantService(agent_executor=failing_executor))

    response = _turn(TestClient(app), "hello")

    assert response.status_code == 502
    assert response.json()["speech"] == "I couldn't reach LexProof just now."
    assert "secret token" not in response.text


def test_adk_streamable_http_client_negotiates_protocol_with_lexproof(monkeypatch):
    import uvicorn
    from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

    monkeypatch.setattr(
        firebase_auth,
        "verify_firebase_token",
        lambda token: {"uid": "voice-protocol-test", "exp": 2_000_000_000},
    )
    app = create_app()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    url = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Local MCP test server did not start"

        toolset = McpToolset(connection_params=StreamableHTTPConnectionParams(
            url=url,
            headers={"Authorization": "Bearer protocol-test-token", "X-Org-Id": "org-protocol-test"},
            timeout=5,
        ))

        async def list_and_read_version():
            tools = await toolset.get_tools()
            sessions = list(toolset._mcp_session_manager._sessions.values())
            assert sessions
            version = sessions[0][0].protocol_version
            await toolset.close()
            return tools, version

        tools, negotiated_version = asyncio.run(list_and_read_version())
        assert tools
        assert negotiated_version == "2025-11-25"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
