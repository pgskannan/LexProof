"""Read-only MCP tools backed by LexProof's existing REST endpoints."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar
from urllib.parse import quote

from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp_types import ToolAnnotations
from pydantic import BaseModel

from ..config import get_settings
from .auth import FirebaseTokenVerifier
from .client import call_api
from .org import resolve_org_id

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ContractItem(BaseModel):
    contract_id: str
    name: str
    counterparty: str | None = None
    status: str | None = None
    passport_id: str | None = None
    passport_status: str | None = None
    verified: bool | None = None


class ContractListResult(BaseModel):
    contracts: list[ContractItem]
    speech: str


class Citation(BaseModel):
    contract_name: str | None = None
    finding_id: str


class AskResult(BaseModel):
    answer: str
    grounded: bool
    citations: list[Citation]
    speech: str


class ProofResult(BaseModel):
    contract_name: str
    verified: bool
    network: str | None = None
    tx_hash: str | None = None
    block_number: int | None = None
    anchored_at: str | None = None
    explorer_url: str | None = None
    checked_at: str
    speech: str


async def _run_tool(
    name: str,
    org_id: str | None,
    operation: Callable[[], Awaitable[T]],
) -> T:
    from mcp.server.auth.middleware.auth_context import get_access_token

    token = get_access_token()
    claims = token.claims if token else None
    uid = (token.subject if token else None) or (claims or {}).get("uid", "unknown")
    started = datetime.now(timezone.utc)
    try:
        result = await operation()
    except ToolError:
        elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        logger.info(
            "MCP tool=%s uid=%s org_id=%s latency_ms=%.1f status=error",
            name, uid, org_id or "unresolved", elapsed_ms,
        )
        raise
    except Exception:
        elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        logger.warning(
            "MCP tool=%s uid=%s org_id=%s latency_ms=%.1f status=error",
            name, uid, org_id or "unresolved", elapsed_ms,
        )
        raise ToolError("LexProof could not complete the request.") from None

    elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    logger.info(
        "MCP tool=%s uid=%s org_id=%s latency_ms=%.1f status=ok",
        name, uid, org_id or "unresolved", elapsed_ms,
    )
    return result


def _one_sentence(text: str) -> str:
    clean = " ".join(text.strip().split())
    match = re.search(r"[.!?](?:\s|$)", clean)
    return clean[:match.end()].strip() if match else clean


def build_mcp_server() -> MCPServer:
    settings = get_settings()
    project_id = settings.firebase_project_id or settings.project_id or "lexproof-local"
    public_url = settings.mcp_public_url.strip().rstrip("/") or "http://localhost:8000"
    auth = AuthSettings(
        issuer_url=f"https://securetoken.google.com/{project_id}",
        resource_server_url=f"{public_url}/mcp",
        validate_token_resource=False,
        required_scopes=["lexproof:read"],
    )
    server = MCPServer(
        name="LexProof",
        instructions=(
            "LexProof answers questions about the user's contracts with cited findings and can check the integrity of on-chain anchored passports. "
            "Keep spoken answers concise and use the speech field for voice responses. "
            "Treat tool results as scoped to the user's organization and never infer facts that the tools did not return. "
            "LexProof does not provide legal advice."
        ),
        token_verifier=FirebaseTokenVerifier(),
        auth=auth,
    )
    annotations = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

    @server.tool(
        title="List contracts",
        description="List contracts visible to the authenticated user in one organization, including passport status.",
        annotations=annotations,
        structured_output=True,
    )
    async def list_contracts(
        org_id: str | None = None,
        limit: int = 10,
        context: Context | None = None,
    ) -> ContractListResult:
        async def operation() -> ContractListResult:
            selected_org = await resolve_org_id(org_id, context)
            rows = await call_api("GET", "/api/contracts", org_id=selected_org)
            items = [
                ContractItem(
                    contract_id=str(row.get("contract_id") or ""),
                    name=str(row.get("name") or "Untitled contract"),
                    counterparty=row.get("counterparty"),
                    status=row.get("status"),
                    passport_id=row.get("passport_id"),
                    passport_status=row.get("passport_status") or row.get("proof_status"),
                    verified=(
                        row.get("verified")
                        if isinstance(row.get("verified"), bool)
                        else str(row.get("passport_status") or row.get("proof_status") or "").casefold()
                        in {"confirmed", "verified", "pass"}
                    ),
                )
                for row in rows[:max(1, min(limit, 100))]
            ]
            verified_count = sum(item.verified is True for item in items)
            speech = f"You have {len(items)} contract{'s' if len(items) != 1 else ''}."
            if verified_count:
                speech += f" {verified_count} have verified proof passports."
            elif items:
                speech += " No verified proof passports were reported."
            return ContractListResult(contracts=items, speech=speech)

        return await _run_tool("list_contracts", org_id, operation)

    @server.tool(
        title="Ask your contracts",
        description="Ask a question answered from the selected organization's contracts and cited findings.",
        annotations=annotations,
        structured_output=True,
    )
    async def ask_contracts(
        question: str,
        org_id: str | None = None,
        context: Context | None = None,
    ) -> AskResult:
        async def operation() -> AskResult:
            selected_org = await resolve_org_id(org_id, context)
            payload = await call_api(
                "POST",
                f"/api/orgs/{quote(selected_org, safe='')}/ask",
                json={"question": question, "history": []},
                org_id=selected_org,
            )
            citations = [
                Citation(
                    contract_name=item.get("contract_name"),
                    finding_id=str(item.get("finding_id") or ""),
                )
                for item in payload.get("citations", [])
                if item.get("finding_id")
            ]
            answer = str(payload.get("answer") or "")
            grounded = bool(payload.get("grounded"))
            if not grounded:
                speech = "This answer is not grounded in your contracts."
            else:
                spoken = _one_sentence(answer)
                cited = len(citations)
                noun = "finding" if cited == 1 else "findings"
                speech = f"{spoken} Based on {cited} cited {noun}." if spoken else f"Based on {cited} cited {noun}."
            return AskResult(answer=answer, grounded=grounded, citations=citations, speech=speech)

        return await _run_tool("ask_contracts", org_id, operation)

    @server.tool(
        title="Verify contract proof",
        description="Recompute a contract passport's integrity and verify its root against the configured blockchain.",
        annotations=annotations,
        structured_output=True,
    )
    async def verify_contract_proof(
        contract_id: str | None = None,
        contract_name: str | None = None,
        org_id: str | None = None,
        context: Context | None = None,
    ) -> ProofResult:
        async def operation() -> ProofResult:
            selected_org = await resolve_org_id(org_id, context)
            rows = await call_api("GET", "/api/contracts", org_id=selected_org)
            if contract_id:
                matches = [row for row in rows if str(row.get("contract_id")) == contract_id]
            elif contract_name:
                matches = [
                    row for row in rows
                    if str(row.get("name") or "").casefold() == contract_name.casefold()
                ]
            else:
                raise ToolError("Pass contract_id or contract_name.")

            if not matches:
                raise ToolError("No matching contract was found in that organization.")
            if len(matches) > 1:
                candidates = ", ".join(str(row.get("name") or "Untitled contract") for row in matches[:5])
                raise ToolError(f"Contract name is ambiguous. Candidates: {candidates}.")

            contract = matches[0]
            name = str(contract.get("name") or "Untitled contract")
            passport_id = contract.get("passport_id")
            checked_at = datetime.now(timezone.utc).isoformat()
            if not passport_id:
                return ProofResult(
                    contract_name=name,
                    verified=False,
                    checked_at=checked_at,
                    speech=f"{name} has no proof passport to verify.",
                )

            result = await call_api(
                "POST",
                f"/api/passports/{quote(str(passport_id), safe='')}/verify",
                org_id=selected_org,
            )
            network = result.get("blockchain_network")
            tx_hash = result.get("transaction_hash")
            verified = result.get("anchor_status") == "PASS"
            explorer_url = (
                f"https://sepolia.etherscan.io/tx/{tx_hash}"
                if verified and tx_hash and network == "ethereum-sepolia"
                else None
            )
            if verified:
                chain = "Sepolia" if network == "ethereum-sepolia" else (network or "the configured network")
                speech = f"{name} is verified. Its passport integrity and on-chain root match on {chain}."
            else:
                statuses = {
                    "NOT_ANCHORED": "no on-chain passport root was found",
                    "NETWORK_ERROR": "the blockchain could not be reached",
                    "INVALID_PROOF": "the on-chain root does not match the passport",
                    "CHAIN_MISMATCH": "the configured blockchain does not match the passport network",
                    "FAIL": "the passport integrity check failed",
                    "UNVERIFIABLE": "the passport integrity could not be fully verified",
                }
                detail = statuses.get(str(result.get("anchor_status")), "verification did not pass")
                speech = f"{name} is not verified because {detail}."
            return ProofResult(
                contract_name=name,
                verified=verified,
                network=network,
                tx_hash=tx_hash,
                block_number=result.get("block_number"),
                anchored_at=result.get("anchored_at"),
                explorer_url=explorer_url,
                checked_at=checked_at,
                speech=speech,
            )

        return await _run_tool("verify_contract_proof", org_id, operation)

    return server