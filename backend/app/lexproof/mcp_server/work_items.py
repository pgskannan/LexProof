"""Read-only MCP tools for upcoming payment obligations and approvals."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import quote

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.server import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel

from .client import call_api
from .org import resolve_org_id

logger = logging.getLogger(__name__)
MAX_CONCURRENT_READS = 8


class ObligationItem(BaseModel):
    obligation_id: str
    contract_name: str
    description: str
    amount: str
    currency: str
    due_date: str | None = None
    status: str
    approval_status: str


class ObligationListResult(BaseModel):
    obligations: list[ObligationItem]
    speech: str


class AvailableAction(BaseModel):
    action_id: str
    label: str


class PendingItem(BaseModel):
    kind: str
    id: str
    title: str
    current_state: str | None = None
    amount: str | None = None
    currency: str | None = None
    available_actions: list[AvailableAction]


class PendingApprovalsResult(BaseModel):
    items: list[PendingItem]
    speech: str


def _parse_due(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.date()
        except ValueError:
            return None


def _amount_decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value or "0").replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal(0)
    return result if result.is_finite() else Decimal(0)


def _money(value: Any, currency: str) -> str:
    amount = _amount_decimal(value)
    rendered = f"{amount:,.2f}" if amount % 1 else f"{amount:,.0f}"
    if currency.upper() == "USD":
        return f"{rendered} dollars"
    return f"{rendered} {currency.upper()}"


async def _contracts(org_id: str, limit: int) -> list[dict[str, Any]]:
    rows = await call_api("GET", "/api/contracts", org_id=org_id)
    return rows[:limit]


async def _payment_views(
    contracts: list[dict[str, Any]],
    org_id: str,
    semaphore: asyncio.Semaphore | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    limiter = semaphore or asyncio.Semaphore(MAX_CONCURRENT_READS)

    async def load(contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        async with limiter:
            view = await call_api(
                "GET",
                f"/api/contracts/{quote(str(contract.get('contract_id') or ''), safe='')}/payments",
                org_id=org_id,
            )
        return contract, view

    return list(await asyncio.gather(*(load(contract) for contract in contracts)))


def _obligation_row(row: dict[str, Any], contract_name: str) -> ObligationItem:
    currency = str(row.get("currency") or "USD").upper()
    return ObligationItem(
        obligation_id=str(row.get("id") or ""),
        contract_name=contract_name,
        description=str(row.get("label") or row.get("trigger_text") or "Payment obligation"),
        amount=str(row.get("amount") or "0"),
        currency=currency,
        due_date=row.get("due_date"),
        status=str(row.get("status") or "UNKNOWN"),
        approval_status=str(row.get("status") or "UNKNOWN"),
    )


def _speech_for_obligations(rows: list[ObligationItem], days_ahead: int) -> str:
    if not rows:
        return f"No payments are due or overdue in the next {days_ahead} days."
    count = len(rows)
    speech = f"{count} payment{'s' if count != 1 else ''} are due in the next {days_ahead} days;"
    largest = max(rows, key=lambda item: _amount_decimal(item.amount))
    due = _parse_due(largest.due_date)
    if due:
        speech += f" the largest is {_money(largest.amount, largest.currency)} to {largest.contract_name} on {due.strftime('%B')} {due.day}."
    else:
        speech += f" the largest is {_money(largest.amount, largest.currency)} for {largest.contract_name}."
    today = datetime.now(timezone.utc).date()
    overdue_count = sum(bool(_parse_due(item.due_date) and _parse_due(item.due_date) < today) for item in rows)
    if overdue_count:
        speech += f" {overdue_count} {'is' if overdue_count == 1 else 'are'} overdue."
    return speech


async def _member_roles(org_id: str) -> list[str]:
    profile = await call_api("GET", "/api/me", org_id=org_id)
    for membership in profile.get("orgs") or []:
        if membership.get("org_id") == org_id and membership.get("member_status") == "active":
            return [str(role) for role in membership.get("roles") or []]
    return []


def register_work_item_tools(
    server: MCPServer,
    annotations: ToolAnnotations,
    contract_resolver: Callable[[list[dict[str, Any]], str | None, str | None], dict[str, Any]],
) -> None:
    async def upcoming_obligations(
        contract_id: str | None = None,
        contract_name: str | None = None,
        days_ahead: int = 30,
        org_id: str | None = None,
        context: Context | None = None,
    ) -> ObligationListResult:
        started = time.perf_counter()
        selected_org = await resolve_org_id(org_id, context)
        if not 0 <= days_ahead <= 365:
            from mcp.server.mcpserver.exceptions import ToolError

            raise ToolError("days_ahead must be between 0 and 365.")

        if contract_id or contract_name:
            contracts = await _contracts(selected_org, 100)
            selected_contracts = [contract_resolver(contracts, contract_id, contract_name)]
        else:
            selected_contracts = await _contracts(selected_org, 25)

        today = datetime.now(timezone.utc).date()
        last_day = today + timedelta(days=days_ahead)
        result: list[ObligationItem] = []
        for contract, view in await _payment_views(selected_contracts, selected_org):
            name = str(contract.get("name") or "Untitled contract")
            for row in view.get("obligations") or []:
                due = _parse_due(row.get("due_date"))
                if due and (due < today or due <= last_day):
                    result.append(_obligation_row(row, name))
        result.sort(key=lambda item: (_parse_due(item.due_date) or date.max, item.contract_name.casefold(), item.obligation_id))
        logger.info(
            "MCP work item tool=upcoming_obligations org_id=%s latency_ms=%.1f",
            selected_org,
            (time.perf_counter() - started) * 1000,
        )
        return ObligationListResult(
            obligations=result,
            speech=_speech_for_obligations(result, days_ahead),
        )

    async def pending_approvals(
        org_id: str | None = None,
        context: Context | None = None,
    ) -> PendingApprovalsResult:
        started = time.perf_counter()
        selected_org = await resolve_org_id(org_id, context)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_READS)
        workflows, roles, contracts = await asyncio.gather(
            call_api(
                "GET",
                f"/api/orgs/{quote(selected_org, safe='')}/workflow-instances",
                params={"status": "in_progress", "limit": 200},
                org_id=selected_org,
            ),
            _member_roles(selected_org),
            _contracts(selected_org, 25),
        )
        role_set = set(roles)
        result: list[PendingItem] = []
        access_token = get_access_token()
        caller_uid = (access_token.subject if access_token else None) or str((access_token.claims if access_token else {}).get("uid") or "")

        instances = workflows.get("items") or []
        definition_ids = list(dict.fromkeys(str(instance.get("definition_id") or "") for instance in instances))

        async def load_definition(definition_id: str) -> tuple[str, dict[str, Any]]:
            async with semaphore:
                definition = await call_api(
                    "GET",
                    f"/api/orgs/{quote(selected_org, safe='')}/workflow-definitions/{quote(definition_id, safe='')}",
                    org_id=selected_org,
                )
            return definition_id, definition

        definition_pairs, payment_views = await asyncio.gather(
            asyncio.gather(*(load_definition(definition_id) for definition_id in definition_ids)),
            _payment_views(contracts, selected_org, semaphore),
        )
        definition_cache = dict(definition_pairs)

        for instance in instances:
            current_state = str(instance.get("current_state") or "")
            definition_id = str(instance.get("definition_id") or "")
            definition = definition_cache.get(definition_id, {})
            transitions = []
            for transition in definition.get("transitions") or []:
                if transition.get("from_state") != current_state:
                    continue
                state_record = next(
                    (state for state in definition.get("states") or [] if state.get("id") == current_state),
                    {},
                )
                if state_record.get("is_terminal"):
                    continue
                allowed_roles = set(transition.get("allowed_roles") or [])
                if allowed_roles and not allowed_roles.intersection(role_set):
                    continue
                if any(instance.get(field) == caller_uid for field in transition.get("requires_not_actor") or []):
                    continue
                transitions.append(AvailableAction(action_id=str(transition.get("id") or ""), label=str(transition.get("action_name") or "Continue")))
            if transitions:
                metadata = instance.get("metadata") or {}
                result.append(PendingItem(
                    kind="workflow",
                    id=str(instance.get("instance_id") or ""),
                    title=str(metadata.get("title") or metadata.get("contract_name") or instance.get("entity_type") or "Workflow approval"),
                    current_state=current_state,
                    available_actions=transitions,
                ))

        if role_set.intersection({"approver", "admin"}):
            for contract, view in payment_views:
                for row in view.get("obligations") or []:
                    status = str(row.get("status") or "").upper()
                    if status not in {"EXTRACTED", "PENDING_APPROVAL", "NEEDS_REVIEW"}:
                        continue
                    if row.get("edited_by") and str(row.get("edited_by")) == caller_uid:
                        continue
                    actions = [AvailableAction(action_id="reject", label="Reject payment")]
                    needs_review = bool(row.get("needs_review_reason") and not row.get("edited_by"))
                    if row.get("payer_email") and not needs_review:
                        actions.insert(0, AvailableAction(action_id="approve", label="Approve payment"))
                    if not actions:
                        continue
                    result.append(PendingItem(
                        kind="payment_obligation",
                        id=str(row.get("id") or ""),
                        title=str(contract.get("name") or "Untitled contract"),
                        amount=str(row.get("amount") or "0"),
                        currency=str(row.get("currency") or "USD").upper(),
                        available_actions=actions,
                    ))

        result.sort(key=lambda item: (item.kind, item.title.casefold(), item.id))
        workflows_count = sum(item.kind == "workflow" for item in result)
        payments_count = sum(item.kind == "payment_obligation" for item in result)
        total = len(result)
        speech = f"You have {total} item{'s' if total != 1 else ''} waiting: {workflows_count} contract approval{'s' if workflows_count != 1 else ''} and {payments_count} payment{'s' if payments_count != 1 else ''}."
        logger.info(
            "MCP work item tool=pending_approvals org_id=%s latency_ms=%.1f",
            selected_org,
            (time.perf_counter() - started) * 1000,
        )
        return PendingApprovalsResult(items=result, speech=speech)

    server.add_tool(
        upcoming_obligations,
        title="Upcoming payment obligations",
        description="Show due and overdue payment obligations from authorized contract payment views.",
        annotations=annotations,
        structured_output=True,
    )
    server.add_tool(
        pending_approvals,
        title="Pending approvals",
        description="List workflow and payment approvals the authenticated user's current organization roles can act on.",
        annotations=annotations,
        structured_output=True,
    )