"""Org-scoped grounded Q&A over persisted contract findings."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..services.ask_contracts import AskContractsService, get_ask_service
from ..services.auth import get_current_org_member
from ..services.vertex_ai import VertexAIError

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
    history = [turn.model_dump() for turn in body.history]
    try:
        result = await _service().ask(org_id, body.question, str(member["uid"]), history=history)
    except VertexAIError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return result
