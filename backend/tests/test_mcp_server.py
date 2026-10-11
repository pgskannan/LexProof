from __future__ import annotations

from contextlib import asynccontextmanager
from importlib import import_module
import json
from typing import Any

import httpx
import pytest
from fastapi import Request

from app.lexproof.api import ask as ask_api
from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
import app.lexproof.main as main_module
from app.lexproof.config import get_settings
from app.lexproof.services import auth as auth_service
from app.lexproof.services import firebase_auth
from app.lexproof.services.ask_contracts import AskContractsService
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

passport_api = import_module("app.lexproof.domains.passport.api.router")

ORG_ID = "org-1"
PASSPORT_ID = "11111111-1111-4111-8111-111111111111"
PROTOCOL_VERSION = "2025-11-25"


class FakeAskService:
    async def ask(self, org_id: str, question: str, uid: str, **kwargs: Any) -> dict[str, Any]:
        if "ungrounded" in question:
            return {"answer": "No contract evidence supports that answer.", "citations": [], "grounded": False}
        return {
            "answer": "The agreement has a 30-day termination notice. It also has a liability cap.",
            "citations": [{"contract_name": "Demo MSA", "finding_id": "finding-1"}],
            "grounded": True,
        }


class FakePassportAnchorService:
    async def verify_passport_root_status(self, passport_id: str, integrity: dict[str, Any]) -> dict[str, Any]:
        return {
            **integrity,
            "passport_id": passport_id,
            "anchor_status": "PASS",
            "blockchain_network": "ethereum-sepolia",
            "transaction_hash": "0xabc123",
            "block_number": 12345,
        }


def _seed_stores() -> None:
    FakeRepository.stores = {
        "organizations": {
            "org-1": {"org_id": "org-1", "name": "Demo", "status": "active"},
            "org-2": {"org_id": "org-2", "name": "Other", "status": "active"},
        },
        "users": {
            "user-1": {"user_id": "user-1", "org_memberships": ["org-1"]},
            "user-2": {"user_id": "user-2", "org_memberships": ["org-2"]},
            "judge-1": {"user_id": "judge-1", "org_memberships": ["org-1"]},
        },
        "organization_invites": {},
        "organizations/org-1/members": {
            "user-1": {"user_id": "user-1", "org_id": "org-1", "roles": ["admin"], "status": "active"},
            "judge-1": {"user_id": "judge-1", "org_id": "org-1", "roles": ["viewer"], "status": "active"},
        },
        "organizations/org-2/members": {
            "user-2": {"user_id": "user-2", "org_id": "org-2", "roles": ["admin"], "status": "active"},
        },
        "contracts": {
            "contract-1": {
                "id": "contract-1",
                "name": "Demo MSA",
                "org_id": "org-1",
                "owner_id": "user-1",
                "current_version_id": "version-1",
                "status": "active",
            },
            "contract-2": {
                "id": "contract-2",
                "name": "No Passport NDA",
                "org_id": "org-1",
                "owner_id": "user-1",
                "status": "active",
            },
        },
        "contract_versions": {
            "version-1": {
                "id": "version-1",
                "passport_id": PASSPORT_ID,
                "contract_id": "contract-1",
                "version_number": 1,
                "analysis_status": "complete",
            },
        },
        "legal_passports": {
            PASSPORT_ID: {"id": PASSPORT_ID, "passport_id": PASSPORT_ID, "contract_id": "contract-1", "org_id": "org-1"},
        },
        "redline_proposals": {},
        "evidence_records": {},
        "evidence_anchors": {},
        "risk_findings": {},
    }


def _make_org_service() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


@pytest.fixture
def mcp_app(monkeypatch):
    _seed_stores()
    org_service = _make_org_service()

    def fake_verify_firebase_token(token: str, settings=None) -> dict[str, Any]:
        if not token.startswith("token-"):
            raise firebase_auth.FirebaseAuthenticationError("Invalid test token")
        return {"uid": token.removeprefix("token-"), "exp": 2_000_000_000}

    monkeypatch.setattr(firebase_auth, "verify_firebase_token", fake_verify_firebase_token)
    monkeypatch.setattr(auth_service, "verify_firebase_token", fake_verify_firebase_token)
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "get_organization_service", lambda: org_service)
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    monkeypatch.setattr(ask_api, "_service", FakeAskService)

    async def fake_load_passport(passport_id: str, user: dict[str, Any]):
        return ({"passport_id": passport_id}, [])

    monkeypatch.setattr(passport_api, "_load_authorized_passport_and_evidence", fake_load_passport)
    monkeypatch.setattr(
        passport_api,
        "verify_passport_integrity",
        lambda passport, evidence_items: {
            "document_status": "PASS",
            "policy_status": "PASS",
            "analysis_status": "PASS",
            "evidence_status": "PASS",
            "passport_hash_status": "PASS",
            "recomputed_passport_hash": "ab" * 32,
        },
    )
    monkeypatch.setattr(
        passport_api,
        "get_passport_root_anchor_service",
        lambda repository: FakePassportAnchorService(),
    )
    monkeypatch.setenv("LEXPROOF_READ_ONLY_UIDS", "judge-1")
    return create_app()


@asynccontextmanager
async def _client(app, token: str, org_id: str = ORG_ID):
    transport = httpx.ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "X-Org-Id": org_id,
    }
    async with app.state.mcp.session_manager.run():
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000", headers=headers) as client:
            yield client


async def _rpc(client: httpx.AsyncClient, request_id: int, method: str, params: dict[str, Any] | None = None):
    headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
    response = await client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


async def _initialize(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "lexproof-tests", "version": "1.0"},
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


@pytest.mark.asyncio
async def test_mcp_initialize_requires_authentication():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
        headers={"Accept": "application/json, text/event-stream"},
    ) as client:
        for path in ("/mcp", "/mcp/"):
            response = await client.post(
                path,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            assert response.status_code == 401
            assert response.headers.get("www-authenticate", "").startswith("Bearer")


def test_mcp_feature_flag_omits_mount(monkeypatch):
    settings = get_settings().model_copy(update={"mcp_enabled": False})
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = create_app()
    assert not any(getattr(route, "name", None) == "mcp" for route in app.routes)


@pytest.mark.asyncio
async def test_mcp_cors_exposes_session_header_only_on_mount(mcp_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp_app),
        base_url="http://localhost:8000",
    ) as client:
        response = await client.options(
            "/mcp",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,x-org-id,mcp-protocol-version,mcp-session-id",
            },
        )
        api_response = await client.options(
            "/api/contracts",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
    assert response.status_code == 200
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert all(
        name in allowed_headers
        for name in ("authorization", "x-org-id", "mcp-protocol-version", "mcp-session-id")
    )
    assert response.headers.get("access-control-expose-headers") == "Mcp-Session-Id"
    assert "access-control-expose-headers" not in api_response.headers


@pytest.mark.asyncio
async def test_authenticated_initialize_negotiates_requested_protocol(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        result = await _initialize(client)
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "LexProof"


@pytest.mark.asyncio
async def test_tools_are_read_only_and_have_speech_output_schemas(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        result = await _rpc(client, 2, "tools/list")
    tools = result["tools"]
    assert {tool["name"] for tool in tools} == {
        "list_contracts", "ask_contracts", "verify_contract_proof",
    }
    for tool in tools:
        assert tool["annotations"]["readOnlyHint"] is True
        assert "speech" in tool["outputSchema"]["properties"]
        assert "context" not in tool["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_list_contracts_is_scoped_by_rest_org_membership(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        own_result = await _rpc(client, 2, "tools/call", {"name": "list_contracts", "arguments": {}})
        client.headers["Authorization"] = "Bearer token-user-2"
        client.headers["X-Org-Id"] = "org-2"
        await _initialize(client)
        other_result = await _rpc(client, 3, "tools/call", {"name": "list_contracts", "arguments": {}})
    own = own_result["structuredContent"]
    assert [row["contract_id"] for row in own["contracts"]] == ["contract-1", "contract-2"]
    assert "2 contracts" in own["speech"]
    assert other_result["structuredContent"]["contracts"] == []


@pytest.mark.asyncio
async def test_ask_contracts_returns_citations_and_ungrounded_speech(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        grounded = await _rpc(
            client,
            2,
            "tools/call",
            {"name": "ask_contracts", "arguments": {"question": "What is the notice period?"}},
        )
        ungrounded = await _rpc(
            client,
            3,
            "tools/call",
            {"name": "ask_contracts", "arguments": {"question": "ungrounded question"}},
        )
    grounded_data = grounded["structuredContent"]
    assert grounded_data["grounded"] is True
    assert grounded_data["citations"][0]["finding_id"] == "finding-1"
    assert grounded_data["speech"].endswith("Based on 1 cited finding.")
    ungrounded_data = ungrounded["structuredContent"]
    assert ungrounded_data["grounded"] is False
    assert "not grounded in your contracts" in ungrounded_data["speech"]


@pytest.mark.asyncio
async def test_verify_contract_proof_reports_verified_and_no_passport(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        verified = await _rpc(
            client,
            2,
            "tools/call",
            {"name": "verify_contract_proof", "arguments": {"contract_id": "contract-1"}},
        )
        no_passport = await _rpc(
            client,
            3,
            "tools/call",
            {"name": "verify_contract_proof", "arguments": {"contract_id": "contract-2"}},
        )
    proof = verified["structuredContent"]
    assert proof["verified"] is True
    assert proof["network"] == "ethereum-sepolia"
    assert proof["tx_hash"] == "0xabc123"
    assert proof["explorer_url"] == "https://sepolia.etherscan.io/tx/0xabc123"
    missing = no_passport["structuredContent"]
    assert missing["verified"] is False
    assert "no proof passport" in missing["speech"]


@pytest.mark.asyncio
async def test_read_only_judge_can_call_all_read_tools(mcp_app):
    async with _client(mcp_app, "token-judge-1") as client:
        await _initialize(client)
        list_result = await _rpc(client, 2, "tools/call", {"name": "list_contracts", "arguments": {}})
        ask_result = await _rpc(
            client,
            3,
            "tools/call",
            {"name": "ask_contracts", "arguments": {"question": "Summarize the notice period."}},
        )
        proof_result = await _rpc(
            client,
            4,
            "tools/call",
            {"name": "verify_contract_proof", "arguments": {"contract_id": "contract-1"}},
        )
    assert "isError" not in list_result or list_result["isError"] is False
    assert "isError" not in ask_result or ask_result["isError"] is False
    assert "isError" not in proof_result or proof_result["isError"] is False


@pytest.mark.asyncio
async def test_rest_authorization_failure_is_a_sanitized_mcp_tool_error(mcp_app):
    async with _client(mcp_app, "token-user-1", org_id="org-2") as client:
        await _initialize(client)
        result = await _rpc(client, 2, "tools/call", {"name": "list_contracts", "arguments": {}})
    assert result["isError"] is True
    assert "access to this organization" in result["content"][0]["text"]
    assert "Not an active member" not in json.dumps(result)