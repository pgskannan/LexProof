"""Money-out approval. Execution replays the stored tool call, once."""

from __future__ import annotations

import json
import logging

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from ...repositories.firestore import FirestoreRepository
from ...services.workflow_catalog import (
    PAYMENT_ACTION_APPROVAL,
    PAYMENT_ACTION_STATES,
    PAYMENT_ACTION_TRANSITIONS,
    payment_action_definition_id,
)
from ...services.workflow_engine import WorkflowEngine, WorkflowError
from .guard import GuardDecision, decide, payment_action_id
from .ledger import load_ledger, record_tool_result
from .obligations import PaymentError
from .receipts import canonical_receipt

logger = logging.getLogger(__name__)

ACTIONS = "payment_actions"


class PaymentActions:
    def __init__(
        self,
        *,
        actions: Any = None,
        invoices: Any = None,
        obligations: Any = None,
        receipts: Any = None,
        evidence: Any = None,
        passports: Any = None,
        workflow: WorkflowEngine | None = None,
        call_tool: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.actions = actions if actions is not None else FirestoreRepository(ACTIONS)
        self.invoices = invoices
        self.obligations = obligations
        self.receipts = receipts
        self.evidence = evidence
        self.passports = passports
        self.workflow = workflow or WorkflowEngine()
        self.call_tool = call_tool
        self.clock = clock or _now

    def list_for_contract(self, org_id: str, contract_id: str) -> list[dict[str, Any]]:
        rows = [
            item
            for item in self.actions.stream()
            if item.get("org_id") == org_id and item.get("contract_id") == contract_id
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""))
        return rows

    def open_request(
        self,
        *,
        org_id: str,
        contract_id: str,
        tool: str,
        args: dict[str, Any],
        requested_by: str,
        reason: str,
        requested_by_email: str = "",
        requested_by_name: str = "",
    ) -> dict[str, Any]:
        name = tool.strip().lower()
        args_hash = payment_action_id(name, args)
        existing = self.actions.get(args_hash)
        if existing:
            return {"id": args_hash, **existing}
        obligation_id = _obligation_from_ledger(self.invoices, self.obligations, contract_id, args)
        self._ensure_definition(org_id, requested_by)
        now = self.clock()
        document = {
            "id": args_hash,
            "org_id": org_id,
            "contract_id": contract_id,
            "tool": name,
            "args": args,
            "args_hash": args_hash,
            "obligation_id": obligation_id,
            "requested_by": requested_by,
            "requested_by_email": requested_by_email,
            "requested_by_name": requested_by_name,
            "reason": reason,
            "status": "in_review",
            "created_at": now,
            "updated_at": now,
        }
        self.actions.set(args_hash, document)
        instance = self.workflow.start_instance(
            org_id,
            payment_action_definition_id(org_id),
            "payment_action",
            args_hash,
            requested_by,
            metadata={"contract_id": contract_id, "tool": name},
        )
        self.actions.set(args_hash, {"workflow_instance_id": instance.get("instance_id"), "updated_at": self.clock()}, merge=True)
        saved = self.actions.get(args_hash) or document
        return {"id": args_hash, **saved}

    def transition(
        self,
        action_id: str,
        transition_id: str,
        actor_id: str,
        roles: list[str],
        comment: str | None = None,
        *,
        actor_email: str = "",
        actor_name: str = "",
    ) -> dict[str, Any]:
        if transition_id == "execute":
            raise PaymentError(400, "Use the execute endpoint to run an approved payment action")
        document = self._get(action_id)
        instance_id = document.get("workflow_instance_id")
        if not instance_id:
            raise PaymentError(409, "Payment action has no workflow")
        try:
            instance = self.workflow.execute_transition(instance_id, transition_id, actor_id, roles, comment)
        except WorkflowError as exc:
            raise PaymentError(403, str(exc)) from exc
        status = str(instance.get("current_state") or document.get("status"))
        now = self.clock()
        update: dict[str, Any] = {"status": status, "updated_at": now, "updated_by": actor_id}
        if status in {"approved", "rejected"}:
            update["resolved_by"] = actor_id
            update["resolved_by_email"] = actor_email
            update["resolved_by_name"] = actor_name
            update["resolved_at"] = now
            if status == "approved":
                update["approved_by"] = actor_id
                update["approved_by_email"] = actor_email
                update["approved_by_name"] = actor_name
        self.actions.set(action_id, update, merge=True)
        return self._get(action_id)

    async def execute(
        self,
        action_id: str,
        actor_id: str,
        roles: list[str],
        *,
        actor_email: str = "",
        actor_name: str = "",
    ) -> dict[str, Any]:
        if self.call_tool is None:
            raise PaymentError(503, "PayPal execution is not configured")

        def claim(transaction: Any) -> dict[str, Any]:
            current = self.actions.get(action_id, transaction=transaction)
            if not current:
                raise PaymentError(404, "Payment action not found")
            status = str(current.get("status") or "")
            if status == "executed":
                raise PaymentError(409, "Payment action already executed")
            if status == "executing":
                raise PaymentError(409, "Payment action is already executing")
            if status != "approved":
                raise PaymentError(409, "Payment action is not approved")
            self.actions.set(
                action_id,
                {"status": "executing", "executing_by": actor_id, "updated_at": self.clock()},
                merge=True,
                transaction=transaction,
            )
            return {"id": action_id, **current}

        try:
            claimed = _transact(self.actions, claim)
        except PaymentError:
            raise
        tool = str(claimed["tool"])
        args = claimed.get("args") if isinstance(claimed.get("args"), dict) else {}
        args_hash = str(claimed.get("args_hash") or "")
        decision = decide(tool, args, [], {args_hash})
        if decision.decision != "allow":
            self._release(action_id)
            raise PaymentError(403, decision.reason)
        try:
            response = await self.call_tool(tool, args)
        except Exception:
            self._release(action_id)
            raise
        transport = "mcp"
        mcp_error = None
        if isinstance(response, dict):
            transport = str(response.pop("_lexproof_transport", "mcp"))
            mcp_error = response.pop("_lexproof_mcp_error", None)
        if isinstance(response, dict) and (response.get("isError") or response.get("error")):
            self._release(action_id)
            from .ledger import paypal_failure

            detail = paypal_failure(response) or ""
            try:
                logger.warning("payment action %s raw PayPal response: %s", action_id, json.dumps(response, default=str)[:1500])
            except (TypeError, ValueError):
                pass
            if not detail or detail == "PayPal error":
                try:
                    detail = json.dumps(response, default=str)[:600]
                except (TypeError, ValueError):
                    detail = str(response)[:600]
            logger.warning("payment action %s: PayPal rejected %s: %s", action_id, tool, detail)
            raise PaymentError(502, f"PayPal rejected the stored tool call: {detail}")
        if self.receipts is not None and self.invoices is not None and self.obligations is not None:
            receipt = canonical_receipt(
                tool,
                args,
                response if isinstance(response, dict) else {},
                decision,
                actor_id,
                str(claimed.get("contract_id") or ""),
            )
            receipt["source"] = "approval"
            receipt["transport"] = transport
            if isinstance(mcp_error, str) and mcp_error:
                receipt["mcp_error"] = mcp_error
            record_tool_result(
                invoices=self.invoices,
                obligations=self.obligations,
                receipts=self.receipts,
                evidence=self.evidence,
                passports=self.passports,
                org_id=str(claimed.get("org_id") or ""),
                contract_id=str(claimed.get("contract_id") or ""),
                actor=actor_id,
                tool=tool,
                args=args,
                response=response,
                decision=GuardDecision("allow", decision.reason, decision.matched_obligation_id),
                receipt=receipt,
                clock=self.clock,
            )
        now = self.clock()
        self.actions.set(
            action_id,
            {
                "status": "executed",
                "executed_by": actor_id,
                "executed_by_email": actor_email,
                "executed_by_name": actor_name,
                "executed_at": now,
                "updated_at": now,
                "paypal_response_id": _response_id(response),
            },
            merge=True,
        )
        instance_id = claimed.get("workflow_instance_id")
        if instance_id:
            try:
                self.workflow.execute_transition(instance_id, "execute", actor_id, roles, "executed stored PayPal call")
            except WorkflowError:
                pass
        return self._get(action_id)

    def _release(self, action_id: str) -> None:
        current = self.actions.get(action_id) or {}
        if current.get("status") == "executing":
            self.actions.set(action_id, {"status": "approved", "updated_at": self.clock()}, merge=True)

    def _get(self, action_id: str) -> dict[str, Any]:
        document = self.actions.get(action_id)
        if not document:
            raise PaymentError(404, "Payment action not found")
        return {"id": action_id, **document}

    def _ensure_definition(self, org_id: str, actor: str) -> None:
        definition_id = payment_action_definition_id(org_id)
        try:
            definition = self.workflow.get_definition(definition_id)
        except WorkflowError:
            self.workflow.create_definition(
                org_id,
                PAYMENT_ACTION_APPROVAL,
                PAYMENT_ACTION_STATES,
                PAYMENT_ACTION_TRANSITIONS,
                actor,
                definition_id=definition_id,
            )
            return
        if definition.get("states") != PAYMENT_ACTION_STATES or definition.get("transitions") != PAYMENT_ACTION_TRANSITIONS:
            self.workflow.update_definition_content(definition_id, PAYMENT_ACTION_STATES, PAYMENT_ACTION_TRANSITIONS)


def _obligation_from_ledger(invoices: Any, obligations: Any, contract_id: str, args: dict[str, Any]) -> str | None:
    if invoices is None or obligations is None:
        return None
    invoice_id = str(args.get("invoice_id") or "").strip()
    if not invoice_id:
        return None
    ledger = load_ledger(invoices, obligations, contract_id)
    entry = ledger.get(invoice_id)
    return entry.obligation_id if entry else None


def _response_id(response: Any) -> str | None:
    if isinstance(response, dict):
        for key in ("id", "refund_id"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _transact(repo: Any, callback: Callable[[Any], Any]) -> Any:
    if hasattr(repo, "run_transaction"):
        return repo.run_transaction(callback)
    return callback(None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
