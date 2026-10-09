"""Sandbox payment obligations, guarded PayPal agent, and money-out approvals."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services.auth import get_current_user, judge_approver_uids, judge_sandbox_contract_id, read_only_uids
from ..services.paypal.book import PaymentBook
from ..services.paypal.obligations import PaymentError
from ..services.paypal.rate_limit import check_agent_rate
from ..services.paypal.checkpoint_service import create_payment_checkpoint

router = APIRouter(tags=["payments"])


class ObligationEditRequest(BaseModel):
    amount: str | None = None
    currency: str | None = None
    due_date: str | None = None
    trigger_text: str | None = None
    payer_email: str | None = None


class AgentRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class TransitionRequest(BaseModel):
    transition_id: str
    comment: str | None = None


def get_payment_book() -> PaymentBook:
    return PaymentBook()


def _changes(body: ObligationEditRequest) -> dict[str, Any]:
    return {key: value for key, value in body.model_dump().items() if value is not None}


def _call(action: Any) -> Any:
    try:
        return action()
    except PaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="PayPal agent timed out") from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="PayPal agent timed out") from exc


@router.post("/contracts/{contract_id}/payments/obligations:extract")
async def extract_obligations(
    contract_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    from ..services.vertex_ai import VertexGeminiProvider

    async def work() -> Any:
        return await book.obligations.extract(contract_id, user, VertexGeminiProvider(book.settings), book.settings.gemini_model)

    try:
        return {"obligations": await work()}
    except PaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/contracts/{contract_id}/payments")
def get_payments(
    contract_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    return _call(lambda: book.view(contract_id, user))


@router.post("/contracts/{contract_id}/payments/checkpoints")
async def create_contract_payment_checkpoint(
    contract_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    uid = str(user.get("uid") or "")
    if uid in read_only_uids():
        raise HTTPException(status_code=403, detail="This is a read-only demo account: you can explore everything, but changes are disabled.")
    try:
        contract = book.obligations._require_roles(contract_id, user, ("contract_owner", "admin"))
        return await create_payment_checkpoint(
            contract_id=contract_id,
            org_id=str(contract.get("org_id") or ""),
            actor_id=uid,
            receipts=book.receipts,
            checkpoints=book.checkpoints,
            evidence=book.obligations.evidence,
            passports=book.obligations.passports,
            settings=book.settings,
        )
    except PaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.patch("/payment-obligations/{obligation_id}")
def edit_obligation(
    obligation_id: str,
    body: ObligationEditRequest,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    return _call(lambda: book.obligations.edit(obligation_id, user, _changes(body)))


@router.post("/payment-obligations/{obligation_id}:approve")
def approve_obligation(
    obligation_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    return _call(lambda: book.obligations.approve(obligation_id, user))


@router.post("/payment-obligations/{obligation_id}:reject")
def reject_obligation(
    obligation_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    return _call(lambda: book.obligations.reject(obligation_id, user))


@router.post("/contracts/{contract_id}/payments/agent")
async def run_payment_agent(
    contract_id: str,
    body: AgentRequest,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    try:
        uid = str(user.get("uid") or "")
        # The hourly cap protects quotas from public judge accounts only;
        # the org's own owners/admins are not throttled.
        if uid in read_only_uids():
            check_agent_rate(uid)
        return await book.run_agent(contract_id, user, body.message, body.session_id)
    except PaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except (TimeoutError, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=504, detail="PayPal agent timed out") from exc


@router.post("/payment-actions/{action_id}/transition")
def transition_payment_action(
    action_id: str,
    body: TransitionRequest,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    def work() -> Any:
        document = book.actions._get(action_id)
        _judge_contract(user, str(document.get("contract_id") or ""))
        roles = _roles(book, str(document.get("org_id") or ""), user)
        return book.actions.transition(
            action_id,
            body.transition_id,
            str(user.get("uid") or ""),
            roles,
            body.comment,
            actor_email=str(user.get("email") or ""),
            actor_name=str(user.get("name") or ""),
        )

    return _call(work)


@router.post("/payment-actions/{action_id}:execute")
async def execute_payment_action(
    action_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    book: PaymentBook = Depends(get_payment_book),
):
    try:
        document = book.actions._get(action_id)
        _judge_contract(user, str(document.get("contract_id") or ""))
        roles = _roles(book, str(document.get("org_id") or ""), user)
        return await book.execute_action(
            action_id,
            str(user.get("uid") or ""),
            roles,
            actor_email=str(user.get("email") or ""),
            actor_name=str(user.get("name") or ""),
        )
    except PaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _judge_contract(user: dict[str, Any], contract_id: str) -> None:
    uid = str(user.get("uid") or "")
    sandbox = judge_sandbox_contract_id()
    if not sandbox or uid not in judge_approver_uids():
        return
    if contract_id != sandbox:
        raise PaymentError(403, "This judge account can approve payments only on the dedicated demo contract.")


def _roles(book: PaymentBook, org_id: str, user: dict[str, Any]) -> list[str]:
    member = book.obligations.members(org_id, str(user.get("uid") or ""))
    if not member:
        raise PaymentError(403, "Not an active member of this organization")
    return list(member.get("roles") or [])
