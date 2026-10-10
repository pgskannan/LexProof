"""Org-scoped grounded Q&A over persisted contract findings."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..services.ask_contracts import AskContractsService, get_ask_service
from ..services.auth import get_current_org_member
from ..config import get_settings
from ..services.auth import read_only_uids
from ..services.paypal.rate_limit import check_judge_interaction_rate
from ..services.llm_base import LLMError

router = APIRouter(prefix="/orgs/{org_id}", tags=["ask"])


class AskHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[AskHistoryTurn] = Field(default_factory=list, max_length=20)


class AskCitation(BaseModel):
    finding_id: str
    evidence_id: str | None = None
    contract_id: str | None = None
    contract_name: str | None = None


class AskResponse(BaseModel):
    answer: str
    citations: list[AskCitation]
    grounded: bool


def _service() -> AskContractsService:
    return get_ask_service()


@router.post("/ask", response_model=AskResponse)
async def ask_contracts(
    org_id: str,
    body: AskRequest,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    uid = str(member["uid"])
    if get_settings().judge_can_analyze and uid in read_only_uids():
        check_judge_interaction_rate(uid)
    history = [turn.model_dump() for turn in body.history]
    try:
        if get_settings().judge_can_analyze and uid in read_only_uids():
            result = await _service().ask(org_id, body.question, uid, history=history, owner_only=True)
        else:
            result = await _service().ask(org_id, body.question, uid, history=history)
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return result
