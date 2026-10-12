from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
import json
from typing import Any

import httpx
import pytest
from fastapi import Request

from app.lexproof.api import ask as ask_api
from app.lexproof.api import contracts as contracts_api
from app.lexproof.api import payments as payments_api
from app.lexproof.main import create_app
import app.lexproof.main as main_module
from app.lexproof.config import get_settings
from app.lexproof.services import auth as auth_service
from app.lexproof.services import firebase_auth
from app.lexproof.services.ask_contracts import AskContractsService
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.mcp_server.server import resolve_contract
from mcp.server.mcpserver.exceptions import ToolError
from tests.fakes import FakeRepository

passport_api = import_module("app.lexproof.domains.passport.api.router")
workflows_api = import_module("app.lexproof.api.workflows")
organizations_api = import_module("app.lexproof.api.organizations")
decisions_module = import_module("app.lexproof.mcp_server.decisions")
work_items_module = import_module("app.lexproof.mcp_server.work_items")
workflow_titles_module = import_module("app.lexproof.mcp_server.workflow_titles")

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
            "reviewer-1": {"user_id": "reviewer-1", "org_memberships": ["org-1"]},
        },
        "organization_invites": {},
        "organizations/org-1/members": {
            "user-1": {"user_id": "user-1", "org_id": "org-1", "roles": ["admin"], "status": "active"},
            "judge-1": {"user_id": "judge-1", "org_id": "org-1", "roles": ["approver"], "status": "active"},
            "reviewer-1": {"user_id": "reviewer-1", "org_id": "org-1", "roles": ["reviewer"], "status": "active"},
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
        "passport_anchors": {},
        "redline_proposals": {},
        "evidence_records": {},
        "evidence_anchors": {},
        "risk_findings": {},
        "payment_obligations": {
            "obligation-overdue": {
                "id": "obligation-overdue", "org_id": "org-1", "contract_id": "contract-1",
                "label": "Annual license", "amount": "12500", "currency": "USD",
                "due_date": (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat(),
                "status": "EXTRACTED", "payer_email": "billing@example.com", "edited_by": "editor-1",
                "updated_at": "2026-10-01T12:00:00+00:00",
            },
            "obligation-upcoming": {
                "id": "obligation-upcoming", "org_id": "org-1", "contract_id": "contract-1",
                "label": "Support renewal", "amount": "3000", "currency": "USD",
                "due_date": (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat(),
                "status": "EXTRACTED", "payer_email": "billing@example.com", "edited_by": "editor-1",
                "updated_at": "2026-10-02T12:00:00+00:00",
            },
            "obligation-later": {
                "id": "obligation-later", "org_id": "org-1", "contract_id": "contract-1",
                "label": "Later support", "amount": "500", "currency": "USD",
                "due_date": (datetime.now(timezone.utc).date() + timedelta(days=60)).isoformat(),
                "status": "EXTRACTED", "payer_email": "billing@example.com", "edited_by": "editor-1",
                "updated_at": "2026-10-03T12:00:00+00:00",
            },
        },
        "payment_settings": {},
        "payment_invoices": {},
        "payment_receipts": {},
        "payment_checkpoints": {},
        "workflow_definitions": {},
        "workflow_instances": {},
        "workflow_instances/workflow-1/history": {},
        "audit_log": {},
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
    monkeypatch.setattr(contracts_api, "PassportAnchorRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "get_organization_service", lambda: org_service)
    monkeypatch.setattr(organizations_api, "get_organization_service", lambda: org_service)
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    monkeypatch.setattr(ask_api, "_service", FakeAskService)
    from app.lexproof.services.paypal.book import PaymentBook
    from app.lexproof.services.paypal.actions import PaymentActions
    from app.lexproof.services.paypal.obligations import PaymentObligations
    from app.lexproof.services.workflow_engine import WorkflowEngine

    audit_events: list[dict[str, Any]] = []
    payment_obligations = PaymentObligations(
        obligations=FakeRepository("payment_obligations"),
        settings_docs=FakeRepository("payment_settings"),
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        evidence=FakeRepository("evidence_records"),
        passports=FakeRepository("legal_passports"),
        members=lambda org_id, uid: org_service.get_active_member(org_id, uid),
        audit=lambda **event: audit_events.append(event),
    )
    payment_actions = PaymentActions(
        actions=FakeRepository("payment_actions"),
        invoices=FakeRepository("payment_invoices"),
        obligations=FakeRepository("payment_obligations"),
        receipts=FakeRepository("payment_receipts"),
        evidence=FakeRepository("evidence_records"),
        passports=FakeRepository("legal_passports"),
    )
    payment_book = PaymentBook(
        obligations=payment_obligations,
        actions=payment_actions,
        invoices=FakeRepository("payment_invoices"),
        receipts=FakeRepository("payment_receipts"),
        checkpoints=FakeRepository("payment_checkpoints"),
    )
    workflow_engine = WorkflowEngine(
        definitions=FakeRepository("workflow_definitions"),
        instances=FakeRepository("workflow_instances"),
        history_factory=lambda instance_id: FakeRepository(f"workflow_instances/{instance_id}/history"),
    )
    workflow_engine.create_definition(
        ORG_ID,
        "Legal review",
        [
            {"id": "review", "name": "Legal review", "is_initial": True},
            {"id": "approved", "name": "Approved", "is_terminal": True},
        ],
        [{"id": "approve-legal", "from_state": "review", "to_state": "approved", "action_name": "Approve legal review", "allowed_roles": ["admin", "approver"], "requires_not_actor": ["created_by"]}],
        "owner-1",
        definition_id="definition-1",
    )
    workflow_engine.start_instance(
        ORG_ID,
        "definition-1",
        "contract",
        "contract-2",
        "originator-1",
        metadata={"title": "Demo MSA legal review", "contract_name": "Demo MSA"},
    )
    monkeypatch.setattr(workflows_api, "get_workflow_engine", lambda: workflow_engine)

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
    monkeypatch.setattr(
        decisions_module,
        "get_settings",
        lambda: type("TestSettings", (), {
            "mcp_confirm_secret": type("TestSecret", (), {"get_secret_value": lambda self: "unit-test-confirm-key"})()
        })(),
    )
    monkeypatch.setenv("LEXPROOF_READ_ONLY_UIDS", "judge-1")
    app = create_app()
    app.dependency_overrides[payments_api.get_payment_book] = lambda: payment_book
    app.state.audit_events = audit_events
    app.state.workflow_engine = workflow_engine
    return app


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
        "list_contracts", "ask_contracts", "verify_contract_proof", "upcoming_obligations",
        "pending_approvals", "prepare_decision", "confirm_decision",
    }
    for tool in tools:
        assert "speech" in tool["outputSchema"]["properties"]
        assert "context" not in tool["inputSchema"]["properties"]
    for name in ("list_contracts", "ask_contracts", "verify_contract_proof", "upcoming_obligations", "pending_approvals", "prepare_decision"):
        assert next(tool for tool in tools if tool["name"] == name)["annotations"]["readOnlyHint"] is True
    confirm = next(tool for tool in tools if tool["name"] == "confirm_decision")
    assert confirm["annotations"]["readOnlyHint"] is False
    assert confirm["annotations"]["destructiveHint"] is False
    assert confirm["annotations"]["idempotentHint"] is False
    assert confirm["annotations"]["openWorldHint"] is False


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
async def test_list_contracts_speech_counts_root_anchors(mcp_app):
    FakeRepository.stores["passport_anchors"][PASSPORT_ID] = {
        "passport_id": PASSPORT_ID,
        "transaction_hash": "0xanchor123",
        "block_number": 12345,
    }
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        anchored = await _rpc(client, 2, "tools/call", {"name": "list_contracts", "arguments": {}})
        FakeRepository.stores["passport_anchors"] = {}
        not_anchored = await _rpc(client, 3, "tools/call", {"name": "list_contracts", "arguments": {}})

    assert anchored["structuredContent"]["speech"] == "You have 2 contracts. 1 have anchored proof passports."
    assert not_anchored["structuredContent"]["speech"] == "You have 2 contracts. None are anchored yet."
    assert "verified" not in anchored["structuredContent"]["speech"].casefold()
    assert "verified" not in not_anchored["structuredContent"]["speech"].casefold()


def test_resolve_contract_accepts_exact_name_and_name_without_extension():
    rows = [{"contract_id": "contract-1", "name": "Demo MSA.docx"}]

    assert resolve_contract(rows, contract_name="Demo MSA.docx")["contract_id"] == "contract-1"
    assert resolve_contract(rows, contract_name="Demo MSA")["contract_id"] == "contract-1"


def test_resolve_contract_normalizes_spoken_contract_names():
    rows = [{"contract_id": "contract-02", "name": "CONTRACT_02_MSA_MediumRisk.docx"}]

    assert resolve_contract(rows, contract_name="contract 02 msa medium risk")["contract_id"] == "contract-02"


def test_resolve_contract_expands_msa_and_reports_ambiguity():
    one_msa = [{"contract_id": "acme-msa", "name": "Acme Master Services Agreement"}]
    two_msas = [
        *one_msa,
        {"contract_id": "beta-msa", "name": "Beta Master Services Agreement"},
    ]

    assert resolve_contract(one_msa, contract_name="master services agreement")["contract_id"] == "acme-msa"
    with pytest.raises(ToolError, match="Acme Master Services Agreement.*Beta Master Services Agreement"):
        resolve_contract(two_msas, contract_name="master services agreement")


def test_resolve_contract_no_match_suggests_list_contracts():
    with pytest.raises(ToolError, match="Try list_contracts"):
        resolve_contract([], contract_name="missing agreement")


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
            {"name": "verify_contract_proof", "arguments": {"contract_name": "Demo MSA.docx"}},
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
@pytest.mark.parametrize(
    ("anchor_status", "expected_speech"),
    [
        ("NOT_ANCHORED", "the passport is not anchored yet"),
        ("INVALID_PROOF", "the fingerprint does not match"),
        ("NETWORK_ERROR", "the network is unavailable"),
    ],
)
async def test_verify_contract_proof_speaks_plain_anchor_failure(
    mcp_app, monkeypatch, anchor_status, expected_speech
):
    class FailedPassportAnchorService:
        async def verify_passport_root_status(self, passport_id, integrity):
            return {
                **integrity,
                "passport_id": passport_id,
                "anchor_status": anchor_status,
                "blockchain_network": "ethereum-sepolia",
                "transaction_hash": None,
                "block_number": None,
            }

    monkeypatch.setattr(
        passport_api,
        "get_passport_root_anchor_service",
        lambda repository: FailedPassportAnchorService(),
    )
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        result = await _rpc(
            client,
            2,
            "tools/call",
            {"name": "verify_contract_proof", "arguments": {"contract_id": "contract-1"}},
        )

    assert result["structuredContent"]["verified"] is False
    assert expected_speech in result["structuredContent"]["speech"]


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


@pytest.mark.asyncio
async def test_upcoming_obligations_includes_overdue_sorts_and_scopes_to_org(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        result = await _rpc(
            client,
            2,
            "tools/call",
            {"name": "upcoming_obligations", "arguments": {"days_ahead": 30}},
        )
        client.headers["Authorization"] = "Bearer token-user-2"
        client.headers["X-Org-Id"] = "org-2"
        await _initialize(client)
        other_org = await _rpc(
            client,
            3,
            "tools/call",
            {"name": "upcoming_obligations", "arguments": {"days_ahead": 30}},
        )
    data = result["structuredContent"]
    assert [item["obligation_id"] for item in data["obligations"]] == ["obligation-overdue", "obligation-upcoming"]
    assert data["obligations"][0]["due_date"] < data["obligations"][1]["due_date"]
    assert "1 is overdue" in data["speech"]
    assert "12,500 dollars" in data["speech"]
    assert other_org["structuredContent"]["obligations"] == []


@pytest.mark.asyncio
async def test_upcoming_obligations_uses_shared_contract_name_resolver(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        result = await _rpc(
            client,
            2,
            "tools/call",
            {"name": "upcoming_obligations", "arguments": {"contract_name": "Demo MSA.docx", "days_ahead": 30}},
        )

    obligations = result["structuredContent"]["obligations"]
    assert [item["obligation_id"] for item in obligations] == ["obligation-overdue", "obligation-upcoming"]


@pytest.mark.asyncio
async def test_pending_approvals_only_includes_actions_allowed_by_rest_roles(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        me = (await client.get("/api/me")).json()
        workflow_rows = (await client.get(f"/api/orgs/{ORG_ID}/workflow-instances", params={"status": "in_progress", "limit": 200})).json()
        payment_rows = (await client.get("/api/contracts/contract-1/payments")).json()
        admin_result = await _rpc(client, 2, "tools/call", {"name": "pending_approvals", "arguments": {}})
        client.headers["Authorization"] = "Bearer token-reviewer-1"
        await _initialize(client)
        reviewer_result = await _rpc(client, 3, "tools/call", {"name": "pending_approvals", "arguments": {}})
    assert any(item.get("org_id") == ORG_ID and item.get("roles") == ["admin"] for item in me.get("orgs", [])), me
    assert workflow_rows.get("items"), workflow_rows
    admin_items = admin_result["structuredContent"]["items"]
    assert {item["kind"] for item in admin_items} == {"workflow", "payment_obligation"}, (admin_result, payment_rows)
    assert all(item["available_actions"] for item in admin_items)
    assert reviewer_result["structuredContent"]["items"] == []


@pytest.mark.asyncio
async def test_pending_approvals_fetches_each_workflow_definition_once(mcp_app, monkeypatch):
    mcp_app.state.workflow_engine.start_instance(
        ORG_ID,
        "definition-1",
        "contract",
        "contract-1",
        "originator-2",
        metadata={"title": "Second legal review", "contract_name": "Demo MSA"},
    )
    original_call_api = work_items_module.call_api
    definition_reads: list[str] = []

    async def tracking_call_api(method, path, *args, **kwargs):
        if "/workflow-definitions/" in path:
            definition_reads.append(path)
        return await original_call_api(method, path, *args, **kwargs)

    monkeypatch.setattr(work_items_module, "call_api", tracking_call_api)
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        result = await _rpc(client, 2, "tools/call", {"name": "pending_approvals", "arguments": {}})

    workflow_items = [item for item in result["structuredContent"]["items"] if item["kind"] == "workflow"]
    assert len(workflow_items) == 2
    assert definition_reads == [f"/api/orgs/{ORG_ID}/workflow-definitions/definition-1"]


@pytest.mark.asyncio
async def test_pending_approvals_resolves_missing_workflow_title_from_contract(mcp_app, monkeypatch):
    instance = next(iter(mcp_app.state.workflow_engine.instances.stream()))
    instance_id = str(instance.get("instance_id") or instance["id"])
    mcp_app.state.workflow_engine.instances.set(
        instance_id,
        {"entity_type": "contract", "entity_id": "contract-2", "metadata": {}},
        merge=True,
    )

    async def fake_contract_lookup(method, path, **kwargs):
        assert method == "GET"
        assert path == "/api/contracts/contract-2"
        return {"contract_id": "contract-2", "name": "No Passport NDA"}

    monkeypatch.setattr(workflow_titles_module, "call_api", fake_contract_lookup)
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        result = await _rpc(client, 2, "tools/call", {"name": "pending_approvals", "arguments": {}})

    workflow_items = [item for item in result["structuredContent"]["items"] if item["kind"] == "workflow"]
    assert any(item["title"] == "Legal review: No Passport NDA" for item in workflow_items), workflow_items
    assert all("contract" not in item["title"].casefold() or "approval" in item["title"].casefold() or ":" in item["title"] for item in workflow_items)


@pytest.mark.asyncio
async def test_workflow_title_resolution_follows_redline_proposal_to_contract(monkeypatch):
    async def fake_call_api(method, path, **kwargs):
        if path == "/api/redline-proposals/proposal-1":
            return {"proposal_id": "proposal-1", "contract_id": "contract-1"}
        if path == "/api/contracts/contract-1":
            return {"contract_id": "contract-1", "name": "Master Services Agreement"}
        raise AssertionError(f"Unexpected route: {path}")

    monkeypatch.setattr(workflow_titles_module, "call_api", fake_call_api)
    monkeypatch.setattr(work_items_module, "call_api", fake_call_api)
    instance = {
        "instance_id": "workflow-1",
        "entity_type": "redline_proposal",
        "entity_id": "proposal-1",
        "metadata": {},
    }
    names = await workflow_titles_module.resolve_workflow_contract_names([instance], ORG_ID)
    definition = {"name": "Legal review", "states": [{"id": "review", "name": "Legal review"}]}

    assert names["workflow-1"] == "Master Services Agreement"
    assert workflow_titles_module.format_workflow_title(instance, definition, names["workflow-1"]) == (
        "Legal review: Master Services Agreement"
    )
    generic_title = workflow_titles_module.format_workflow_title(instance, definition, None)
    generic_speech_subject = workflow_titles_module.workflow_subject(instance, definition, None)
    assert generic_title == "Contract approval"
    assert "redline_proposal" not in generic_title
    assert "redline_proposal" not in generic_speech_subject


def test_decision_action_names_map_to_natural_present_and_past_tense():
    assert decisions_module.action_verbs("approve-legal", "Approve legal review") == (
        "approve", "approved", "legal review"
    )
    assert decisions_module.action_verbs("reject-finance", "Reject finance review") == (
        "reject", "rejected", "finance review"
    )
    assert decisions_module.action_verbs("request_changes", "Request changes") == (
        "request changes to", "requested changes to", None
    )
    assert decisions_module.action_verbs("submit_for_review", "Submit for review") == (
        "submit", "submitted", None
    )
    assert decisions_module.action_verbs("escalate", "Escalate review") == (
        "complete", "completed", "escalate review"
    )


def test_workflow_decision_speech_is_natural_and_never_exposes_entity_slug():
    instance = {
        "instance_id": "workflow-1",
        "entity_type": "redline_proposal",
        "entity_id": "proposal-1",
        "current_state": "review",
        "metadata": {},
    }
    definition = {
        "name": "Legal review",
        "states": [{"id": "review", "name": "Legal review"}],
    }
    infinitive, _past, subject, confirmation = decisions_module.workflow_decision_phrases(
        "approve-legal", "Approve legal review", instance, definition, "Master Services Agreement"
    )

    assert subject == "the legal review for the Master Services Agreement"
    assert confirmation == (
        "Done. You approved the legal review for the Master Services Agreement. "
        "It's recorded in the workflow history."
    )
    assert decisions_module.prepared_decision_speech(infinitive, subject) == (
        "Ready to approve the legal review for the Master Services Agreement. "
        "Say confirm to proceed. Nothing has changed yet."
    )
    assert "redline_proposal" not in confirmation


def test_payment_decision_speech_uses_amount_and_counterparty():
    obligation = {"label": "monthly fee", "amount": "12500.00"}
    summary, speech = decisions_module.confirmed_payment_speech(
        "approve", obligation, "Acme Master Services Agreement"
    )

    assert summary == "Approved the 12,500 dollar Acme monthly fee payment"
    assert speech == (
        "Done. You approved the 12,500 dollar Acme monthly fee payment. "
        "It's recorded in the audit log."
    )


@pytest.mark.asyncio
async def test_prepare_confirm_records_workflow_history_and_payment_audit(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        pending = await _rpc(client, 2, "tools/call", {"name": "pending_approvals", "arguments": {}})
        workflow = next(item for item in pending["structuredContent"]["items"] if item["kind"] == "workflow")
        workflow_prepared = await _rpc(
            client,
            3,
            "tools/call",
            {"name": "prepare_decision", "arguments": {
                "kind": "workflow", "item_id": workflow["id"], "action_id": "approve-legal", "comment": "Reviewed"}},
        )
        workflow_confirmation = workflow_prepared["structuredContent"]
        assert workflow_confirmation["speech"].endswith("Nothing has changed yet.")
        workflow_result = await _rpc(
            client,
            4,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": workflow_confirmation["confirmation_code"]}},
        )
        assert workflow_result["structuredContent"]["success"] is True
        instance_after = mcp_app.state.workflow_engine.get_instance(workflow["id"])
        assert instance_after["current_state"] == "approved"
        assert len(mcp_app.state.workflow_engine.get_instance_history(workflow["id"])) == 1

        payment_prepared = await _rpc(
            client,
            5,
            "tools/call",
            {"name": "prepare_decision", "arguments": {
                "kind": "payment_obligation", "item_id": "obligation-upcoming", "action_id": "approve"}},
        )
        payment_confirmation = payment_prepared["structuredContent"]
        payment_result = await _rpc(
            client,
            6,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": payment_confirmation["confirmation_code"]}},
        )
    assert payment_result["structuredContent"]["success"] is True
    assert FakeRepository.stores["payment_obligations"]["obligation-upcoming"]["status"] == "APPROVED"
    assert any(event["action"] == "payment_obligation.approved" for event in mcp_app.state.audit_events)


@pytest.mark.asyncio
async def test_confirmation_rejects_tampered_replayed_and_wrong_user_tokens(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        prepared = await _rpc(
            client,
            2,
            "tools/call",
            {"name": "prepare_decision", "arguments": {
                "kind": "payment_obligation", "item_id": "obligation-upcoming", "action_id": "approve"}},
        )
        confirmation = prepared["structuredContent"]
        token = confirmation["confirmation_token"]
        tampered_token = token[:-1] + ("B" if token[-1] != "B" else "C")
        tampered = await _rpc(
            client,
            3,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": tampered_token}},
        )
        assert tampered["isError"] is True
        assert FakeRepository.stores["payment_obligations"]["obligation-upcoming"]["status"] == "EXTRACTED"

        client.headers["Authorization"] = "Bearer token-user-2"
        client.headers["X-Org-Id"] = "org-2"
        await _initialize(client)
        wrong_user = await _rpc(
            client,
            4,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": confirmation["confirmation_token"]}},
        )
        assert wrong_user["isError"] is True

        client.headers["Authorization"] = "Bearer token-user-1"
        client.headers["X-Org-Id"] = ORG_ID
        await _initialize(client)
        confirmed = await _rpc(
            client,
            5,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": confirmation["confirmation_token"]}},
        )
        replayed = await _rpc(
            client,
            6,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": confirmation["confirmation_token"]}},
        )
    assert confirmed["structuredContent"]["success"] is True
    assert replayed["isError"] is True
    assert FakeRepository.stores["payment_obligations"]["obligation-upcoming"]["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_confirmation_rejects_expired_and_changed_workflow(mcp_app, monkeypatch):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        pending = await _rpc(client, 2, "tools/call", {"name": "pending_approvals", "arguments": {}})
        workflow = next(item for item in pending["structuredContent"]["items"] if item["kind"] == "workflow")
        prepared = await _rpc(
            client,
            3,
            "tools/call",
            {"name": "prepare_decision", "arguments": {"kind": "workflow", "item_id": workflow["id"], "action_id": "approve-legal"}},
        )
        code = prepared["structuredContent"]["confirmation_code"]
        mcp_app.state.workflow_engine.instances.set(workflow["id"], {"updated_at": "changed-after-prepare"}, merge=True)
        changed = await _rpc(client, 4, "tools/call", {"name": "confirm_decision", "arguments": {"confirmation_code": code}})
        assert changed["isError"] is True
        assert "changed since you asked" in changed["content"][0]["text"]
        assert mcp_app.state.workflow_engine.get_instance(workflow["id"])["current_state"] == "review"

        second_prepared = await _rpc(
            client,
            5,
            "tools/call",
            {"name": "prepare_decision", "arguments": {"kind": "payment_obligation", "item_id": "obligation-overdue", "action_id": "reject"}},
        )
        expires_at = datetime.fromisoformat(second_prepared["structuredContent"]["expires_at"]).timestamp()
        monkeypatch.setattr(decisions_module.time, "time", lambda: expires_at + 1)
        expired = await _rpc(
            client,
            6,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": second_prepared["structuredContent"]["confirmation_code"]}},
        )
    assert expired["isError"] is True
    assert "expired" in expired["content"][0]["text"].lower()
    assert FakeRepository.stores["payment_obligations"]["obligation-overdue"]["status"] == "EXTRACTED"


@pytest.mark.asyncio
async def test_short_code_is_user_bound_and_read_only_judge_cannot_confirm(mcp_app):
    async with _client(mcp_app, "token-user-1") as client:
        await _initialize(client)
        prepared = await _rpc(
            client,
            2,
            "tools/call",
            {"name": "prepare_decision", "arguments": {"kind": "payment_obligation", "item_id": "obligation-upcoming", "action_id": "reject"}},
        )
        code = prepared["structuredContent"]["confirmation_code"]
        client.headers["Authorization"] = "Bearer token-user-2"
        client.headers["X-Org-Id"] = "org-2"
        await _initialize(client)
        wrong_user_code = await _rpc(client, 3, "tools/call", {"name": "confirm_decision", "arguments": {"confirmation_code": code}})

        client.headers["Authorization"] = "Bearer token-judge-1"
        client.headers["X-Org-Id"] = ORG_ID
        await _initialize(client)
        judge_prepared = await _rpc(
            client,
            4,
            "tools/call",
            {"name": "prepare_decision", "arguments": {"kind": "payment_obligation", "item_id": "obligation-upcoming", "action_id": "approve"}},
        )
        judge_confirmed = await _rpc(
            client,
            5,
            "tools/call",
            {"name": "confirm_decision", "arguments": {"confirmation_code": judge_prepared["structuredContent"]["confirmation_code"]}},
        )
    assert wrong_user_code["isError"] is True
    assert judge_confirmed["structuredContent"]["success"] is False
    assert "read-only demo account" in judge_confirmed["structuredContent"]["speech"]
    assert FakeRepository.stores["payment_obligations"]["obligation-upcoming"]["status"] == "EXTRACTED"