from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..services.auth import get_current_user, read_only_uids
from ..services.paypal.rate_limit import check_judge_interaction_rate
from ..services.voice_assistant import VoiceAssistantFailure, VoiceAssistantService

router = APIRouter(prefix="/voice", tags=["voice"])
_assistant = VoiceAssistantService()


class VoiceTurnRequest(BaseModel):
    utterance: str = Field(min_length=1, max_length=500)
    session_id: str | None = None
    org_id: str | None = None


class VoiceToolTrace(BaseModel):
    tool: str
    arguments_summary: str
    ok: bool
    latency_ms: int


class VoiceTurnResponse(BaseModel):
    session_id: str
    speech: str
    display_text: str
    tool_trace: list[VoiceToolTrace]
    awaiting_confirmation: dict[str, Any] | None = None


@router.post("/turn", response_model=VoiceTurnResponse)
async def voice_turn(
    body: VoiceTurnRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
):
    uid = str(user.get("uid") or "")
    if get_settings().judge_can_analyze and uid in read_only_uids():
        check_judge_interaction_rate(uid)
    utterance = body.utterance.strip()
    if not utterance:
        raise HTTPException(status_code=400, detail="utterance is required")
    authorization = request.headers.get("Authorization", "")
    org_id = request.headers.get("X-Org-Id") or body.org_id or user.get("org_id") or None
    try:
        result = await _assistant.turn(
            uid=uid,
            utterance=utterance,
            authorization=authorization,
            org_id=str(org_id) if org_id else None,
            session_id=body.session_id,
        )
    except VoiceAssistantFailure as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=VoiceTurnResponse(
                session_id=exc.session_id,
                speech=exc.speech,
                display_text=exc.speech,
                tool_trace=exc.tool_trace,
                awaiting_confirmation=None,
            ).model_dump(),
        )
    return VoiceTurnResponse(**result)