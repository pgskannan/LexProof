"""Facade the payments API uses to load a mandate and run a guarded turn."""

from __future__ import annotations

from typing import Any

from ...config import LexProofSettings, get_settings
from .actions import PaymentActions
from .agent import PayPalAgentGuard, call_paypal_tool, run_paypal_turn, transport_for_url
from .auth import PayPalTokenProvider
from .guard import ApprovedObligation
from .ledger import default_invoices, default_receipts, load_ledger, record_tool_result
from .obligations import AGENT_ROLES, PaymentError, PaymentObligations

AGENT_TIMEOUT_SECONDS = 60


class PaymentBook:
    def __init__(
        self,
        *,
        obligations: PaymentObligations | None = None,
        actions: PaymentActions | None = None,
        invoices: Any = None,
        receipts: Any = None,
        settings: LexProofSettings | None = None,
        token_provider: PayPalTokenProvider | None = None,
        run_turn: Any = None,
        call_tool: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.obligations = obligations or PaymentObligations()
        self.invoices = invoices if invoices is not None else default_invoices()
        self.receipts = receipts if receipts is not None else default_receipts()
        self.actions = actions or PaymentActions(
            invoices=self.invoices,
            obligations=self.obligations.obligations,
            receipts=self.receipts,
            evidence=self.obligations.evidence,
            passports=self.obligations.passports,
        )
        self._token_provider = token_provider
        self._run_turn = run_turn or run_paypal_turn
        self._call_tool = call_tool

    def view(self, contract_id: str, user: dict[str, Any]) -> dict[str, Any]:
        payload = self.obligations.payment_view(contract_id, user)
        org_id = str(payload["org_id"])
        payload["invoices"] = [
            item for item in self.invoices.stream() if item.get("org_id") == org_id and item.get("contract_id") == contract_id
        ]
        payload["receipts"] = [
            item for item in self.receipts.stream() if item.get("org_id") == org_id and item.get("contract_id") == contract_id
        ]
        payload["actions"] = self.actions.list_for_contract(org_id, contract_id)
        return payload

    async def run_agent(self, contract_id: str, user: dict[str, Any], message: str, session_id: str | None = None) -> dict[str, Any]:
        contract = self.obligations._require_roles(contract_id, user, AGENT_ROLES)
        if not self.settings.has_paypal_configuration():
            raise PaymentError(503, "PayPal is not configured")
        org_id = str(contract.get("org_id"))
        actor = str(user.get("uid") or "")
        mandate = [
            ApprovedObligation(
                id=str(item["id"]),
                currency=str(item.get("currency") or ""),
                amount=str(item.get("amount") or "0"),
                payer_email=str(item.get("payer_email") or ""),
                status=str(item.get("status") or ""),
            )
            for item in self.obligations.approved_for_guard(contract_id)
        ]
        ledger = load_ledger(self.invoices, self.obligations.obligations, contract_id)
        recorded: list[dict[str, Any]] = []

        async def hook(tool: str, args: dict[str, Any], response: Any, decision: Any, receipt: dict[str, Any]) -> None:
            stored = record_tool_result(
                invoices=self.invoices,
                obligations=self.obligations.obligations,
                receipts=self.receipts,
                evidence=self.obligations.evidence,
                passports=self.obligations.passports,
                org_id=org_id,
                contract_id=contract_id,
                actor=actor,
                tool=tool,
                args=args,
                response=response,
                decision=decision,
                receipt=receipt,
            )
            action_id = None
            if decision.decision == "needs_approval":
                opened = self.actions.open_request(
                    org_id=org_id,
                    contract_id=contract_id,
                    tool=tool,
                    args=args,
                    requested_by=actor,
                    reason=decision.reason,
                )
                action_id = opened.get("id")
            recorded.append(
                {
                    "tool": tool,
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "matched_obligation_id": decision.matched_obligation_id,
                    "receipt_id": stored.get("id"),
                    "action_id": action_id,
                }
            )

        guard = PayPalAgentGuard(
            mandate=mandate,
            approvals=set(),
            actor=actor,
            contract_id=contract_id,
            invoice_ledger=ledger,
            result_hook=hook,
        )
        token = await self._access_token()
        url = self.settings.paypal_mcp_url
        turn = await self._run_turn(
            model=self.settings.gemini_model,
            mcp_url=url,
            access_token=token,
            transport=transport_for_url(url),
            guard=guard,
            message=message,
            user_id=actor,
            session_id=session_id,
            timeout_seconds=AGENT_TIMEOUT_SECONDS,
        )
        return {"session_id": turn.get("session_id"), "text": turn.get("text") or "", "tool_calls": recorded}

    async def execute_action(self, action_id: str, actor_id: str, roles: list[str]) -> dict[str, Any]:
        if self.actions.call_tool is None:
            token_holder: dict[str, str] = {}

            async def _call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
                if "token" not in token_holder:
                    token_holder["token"] = await self._access_token()
                caller = self._call_tool or call_paypal_tool
                return await caller(self.settings.paypal_mcp_url, token_holder["token"], tool, args)

            self.actions.call_tool = _call
        return await self.actions.execute(action_id, actor_id, roles)

    async def _access_token(self) -> str:
        if not self.settings.has_paypal_configuration():
            raise PaymentError(503, "PayPal is not configured")
        provider = self._token_provider or PayPalTokenProvider(
            self.settings.paypal_client_id,
            self.settings.paypal_client_secret.get_secret_value(),
        )
        try:
            token = await provider.get_access_token()
        finally:
            if self._token_provider is None:
                await provider.aclose()
        return token
