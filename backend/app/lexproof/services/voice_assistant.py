from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from ..config import get_settings

logger = logging.getLogger(__name__)
APP_NAME = "lexproof_voice"
TURN_TIMEOUT_SECONDS = 45
_CONFIRM_UTTERANCE = re.compile(r"^(yes|yeah|confirm|approve it|go ahead)\b", re.IGNORECASE)
_BLOCKED_CONFIRMATION_SPEECH = "I need you to say 'confirm' first. Nothing has changed."
_AGENT_INSTRUCTION = (
    "You are Ask Lexi, LexProof's voice assistant. Use the available LexProof MCP tools to answer. "
    "Speak at most two short sentences and prefer a tool's speech field verbatim. Never provide legal advice. "
    "If the contract is ambiguous, ask one concise clarifying question and do not guess. "
    "For approvals, call prepare_decision, read its summary and consequences briefly, then stop and wait for a later turn. "
    "Only call confirm_decision after the user explicitly confirms in a later turn; pass the prepared short confirmation code, "
    "never the full confirmation token. Do not claim an action succeeded unless its tool reports success."
)


class VoiceAssistantFailure(Exception):
    def __init__(
        self,
        status_code: int,
        speech: str,
        tool_trace: list[dict[str, Any]],
        session_id: str,
    ):
        self.status_code = status_code
        self.speech = speech
        self.tool_trace = tool_trace
        self.session_id = session_id
        super().__init__(speech)


class VoiceSessionStore:
    def __init__(self, *, idle_minutes: int = 30, max_turns: int = 20):
        self.idle_minutes = idle_minutes
        self.max_turns = max_turns
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def create(self, uid: str) -> dict[str, Any]:
        session_id = secrets.token_urlsafe(18)
        entry = {
            "uid": uid,
            "session_id": session_id,
            "turn_count": 0,
            "expires_at": self._now() + timedelta(minutes=self.idle_minutes),
            "pending": None,
        }
        self.sessions[(uid, session_id)] = entry
        return entry

    def get(self, uid: str, session_id: str) -> dict[str, Any] | None:
        entry = self.sessions.get((uid, session_id))
        if entry is None:
            for (owner_uid, stored_id), other in list(self.sessions.items()):
                if stored_id == session_id and owner_uid != uid:
                    self.sessions.pop((owner_uid, stored_id), None) if other["expires_at"] <= self._now() else None
                    break
            return None
        if entry["expires_at"] <= self._now():
            self.sessions.pop((uid, session_id), None)
            return None
        return entry

    def resolve(self, uid: str, session_id: str | None) -> dict[str, Any]:
        if not session_id:
            return self.create(uid)
        entry = self.get(uid, session_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Voice session not found.")
        if entry["turn_count"] >= self.max_turns:
            raise HTTPException(status_code=429, detail="Session limit reached. Start a new session.")
        return entry

    def finish_turn(self, entry: dict[str, Any]) -> None:
        entry["turn_count"] += 1
        entry["expires_at"] = self._now() + timedelta(minutes=self.idle_minutes)
        pending = entry.get("pending")
        if pending and pending.get("turn_number", 0) < entry["turn_count"]:
            entry["pending"] = None


class VoiceToolGuard:
    def __init__(
        self,
        *,
        entry: dict[str, Any],
        utterance: str,
        bearer_token: str,
        turn_number: int,
    ):
        self.entry = entry
        self.utterance = utterance
        self.bearer_token = bearer_token
        self.turn_number = turn_number
        self.trace: list[dict[str, Any]] = []
        self._started: dict[str, float] = {}
        self._trace_index: dict[str, int] = {}
        self.tool_speech: list[str] = []
        self.speech_override: str | None = None

    async def before_tool(self, tool: Any, args: Any, tool_context: Any) -> dict[str, Any] | None:
        name = _tool_name(tool)
        payload = args if isinstance(args, dict) else {}
        call_id = _call_id(tool_context) or f"{name}:{len(self.trace)}"
        started = time.perf_counter()
        summary = _safe_json(payload, self.bearer_token)
        record = {
            "tool": name,
            "arguments_summary": summary[:500],
            "ok": False,
            "latency_ms": 0,
        }
        self._trace_index[call_id] = len(self.trace)
        self._started[call_id] = started
        self.trace.append(record)

        if name == "confirm_decision":
            pending = self.entry.get("pending")
            supplied = str(payload.get("confirmation_code") or "").strip()
            is_previous_turn = bool(pending and pending.get("turn_number") == self.turn_number - 1)
            is_unexpired = bool(pending and pending.get("expires_at_epoch", 0) > int(time.time()))
            phrase_matches = bool(_CONFIRM_UTTERANCE.search(self.utterance.strip()))
            short_code = str((pending or {}).get("short_code") or "")
            code_spoken = bool(short_code and re.search(rf"(?<![A-Za-z0-9]){re.escape(short_code)}(?![A-Za-z0-9])", self.utterance, re.IGNORECASE))
            argument_matches = bool(short_code and supplied.casefold() == short_code.casefold())
            if not (is_previous_turn and is_unexpired and (phrase_matches or code_spoken) and argument_matches):
                self.speech_override = _BLOCKED_CONFIRMATION_SPEECH
                self.trace[-1]["arguments_summary"] = _safe_json(payload, self.bearer_token, force_confirmation_redaction=True)[:500]
                self.trace[-1]["latency_ms"] = max(0, int((time.perf_counter() - started) * 1000))
                return {"blocked": True, "speech": _BLOCKED_CONFIRMATION_SPEECH}
        return None

    async def after_tool(self, tool: Any, args: Any, tool_context: Any, tool_response: Any) -> None:
        name = _tool_name(tool)
        call_id = _call_id(tool_context) or f"{name}:{max(0, len(self.trace) - 1)}"
        index = self._trace_index.get(call_id)
        if index is None:
            return
        payload = _as_payload(tool_response)
        is_error = bool(payload.get("isError") or payload.get("error") or payload.get("blocked"))
        self.trace[index]["ok"] = not is_error
        started = self._started.pop(call_id, time.perf_counter())
        self.trace[index]["latency_ms"] = max(0, int((time.perf_counter() - started) * 1000))
        speech = payload.get("speech")
        if isinstance(speech, str) and speech.strip():
            self.tool_speech.append(_redact_text(speech, self.bearer_token))

        if name == "prepare_decision" and not is_error:
            code = str(payload.get("confirmation_code") or payload.get("short_code") or "").strip()
            expiry = _expiry_epoch(payload.get("expires_at"))
            if re.fullmatch(r"[A-Za-z0-9]{4,12}", code) and expiry > int(time.time()):
                self.entry["pending"] = {
                    "short_code": code,
                    "summary": _redact_text(str(payload.get("summary") or "Approval decision"), self.bearer_token),
                    "expires_at": str(payload.get("expires_at") or ""),
                    "expires_at_epoch": expiry,
                    "turn_number": self.turn_number,
                }
        elif name == "confirm_decision" and not is_error:
            self.entry["pending"] = None


def _tool_name(tool: Any) -> str:
    value = getattr(tool, "name", None)
    return str(value if value is not None else tool)


def _call_id(context: Any) -> str:
    return str(getattr(context, "function_call_id", None) or "")


def _expiry_epoch(value: Any) -> int:
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError, OverflowError):
        try:
            return int(value)
        except (ValueError, TypeError, OverflowError):
            return 0


def _as_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        structured = value.get("structuredContent")
        if isinstance(structured, dict):
            return {**value, **structured}
        output = dict(value)
        for block in value.get("content") or []:
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if not isinstance(text, str):
                continue
            try:
                decoded = json.loads(text)
            except (ValueError, TypeError):
                continue
            if isinstance(decoded, dict):
                output.update(decoded)
        return output
    dumped = getattr(value, "model_dump", None)
    if callable(dumped):
        try:
            return _as_payload(dumped())
        except Exception:
            return {}
    return {}


def _safe_json(value: Any, bearer_token: str, *, force_confirmation_redaction: bool = False) -> str:
    def clean(item: Any, key: str = "") -> Any:
        if isinstance(item, dict):
            return {str(child_key): clean(child, str(child_key).casefold()) for child_key, child in item.items()}
        if isinstance(item, list):
            return [clean(child, key) for child in item]
        if isinstance(item, str):
            if key in {"authorization", "access_token", "bearer_token", "confirmation_token", "token"}:
                return "[redacted]"
            if key in {"confirmation_code", "short_code"} and (force_confirmation_redaction or "." in item or len(item) > 12):
                return "[redacted]"
            return _redact_text(item, bearer_token)
        return item

    try:
        return json.dumps(clean(value), sort_keys=True, default=str)
    except (TypeError, ValueError):
        return "[redacted]"


def _redact_text(value: str, bearer_token: str) -> str:
    result = value.replace(bearer_token, "[redacted]") if bearer_token else value
    result = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", result)
    result = re.sub(r"(?i)(confirmation_token|access_token|authorization|token)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", result)
    result = re.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])", "[redacted]", result)
    return result


def _short_speech(value: str) -> str:
    clean = " ".join(value.strip().split())
    sentences = re.findall(r"[^.!?]+[.!?]?(?:\s|$)", clean)
    concise = []
    for sentence in sentences[:2]:
        sentence = sentence.strip()
        if len(sentence) > 220:
            sentence = sentence[:217].rsplit(" ", 1)[0].rstrip(".!?") + "..."
        concise.append(sentence)
    selected = " ".join(concise).strip()
    return selected[:480]


def _is_mcp_connection_failure(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, OSError)):
        return True
    name = type(exc).__name__.casefold()
    module = type(exc).__module__.casefold()
    return (
        any(part in name for part in ("connect", "transport", "mcpconnection", "closedresource"))
        or ("timeout" in name and module.startswith(("httpx", "httpx2", "mcp.")))
        or module.startswith("mcp.")
    )


def _mcp_url() -> str:
    configured = get_settings().mcp_public_url.strip()
    if not configured or configured == "http://localhost:8000":
        configured = "http://127.0.0.1:8000"
    return configured.rstrip("/") if configured.rstrip("/").endswith("/mcp") else f"{configured.rstrip('/')}/mcp"


async def _run_adk_agent(
    *,
    utterance: str,
    uid: str,
    session_id: str,
    authorization: str,
    org_id: str | None,
    guard: VoiceToolGuard,
) -> dict[str, str]:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, GenerateContentConfig, Part
    from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
    from ..services.paypal.agent import use_vertex_ai

    global _ADK_SESSIONS
    use_vertex_ai()
    headers = {"Authorization": authorization}
    if org_id:
        headers["X-Org-Id"] = org_id
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=_mcp_url(),
            headers=headers,
            timeout=30,
            sse_read_timeout=60,
        )
    )
    settings = get_settings()
    agent = Agent(
        name=APP_NAME,
        model=settings.voice_model,
        description="LexProof voice assistant for the authenticated user's organization.",
        instruction=_AGENT_INSTRUCTION,
        generate_content_config=GenerateContentConfig(temperature=0),
        tools=[toolset],
        before_tool_callback=guard.before_tool,
        after_tool_callback=guard.after_tool,
    )
    if _ADK_SESSIONS is None:
        _ADK_SESSIONS = InMemorySessionService()
    sessions = _ADK_SESSIONS
    session = await sessions.get_session(app_name=APP_NAME, user_id=uid, session_id=session_id)
    if session is None:
        session = await sessions.create_session(app_name=APP_NAME, user_id=uid, session_id=session_id)
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=sessions)

    async def run() -> str:
        content = Content(role="user", parts=[Part(text=utterance)])
        outputs: list[str] = []
        async for event in runner.run_async(user_id=uid, session_id=session_id, new_message=content):
            event_content = getattr(event, "content", None)
            for part in getattr(event_content, "parts", None) or []:
                text = getattr(part, "text", None)
                if isinstance(text, str) and text.strip():
                    outputs.append(text.strip())
        return "\n".join(outputs)

    try:
        return {"display_text": await run()}
    finally:
        close = getattr(toolset, "close", None)
        if callable(close):
            closed = close()
            if hasattr(closed, "__await__"):
                await closed


_ADK_SESSIONS: Any = None
AgentExecutor = Callable[..., Awaitable[dict[str, Any]]]


class VoiceAssistantService:
    def __init__(
        self,
        *,
        sessions: VoiceSessionStore | None = None,
        agent_executor: AgentExecutor | None = None,
        timeout_seconds: float = TURN_TIMEOUT_SECONDS,
    ):
        self.sessions = sessions or VoiceSessionStore()
        self.agent_executor = agent_executor or _run_adk_agent
        self.timeout_seconds = timeout_seconds

    async def turn(
        self,
        *,
        uid: str,
        utterance: str,
        authorization: str,
        org_id: str | None,
        session_id: str | None,
    ) -> dict[str, Any]:
        entry = self.sessions.resolve(uid, session_id)
        turn_number = entry["turn_count"] + 1
        pending = entry.get("pending")
        if pending and pending.get("turn_number", 0) < entry["turn_count"]:
            entry["pending"] = None
        guard = VoiceToolGuard(
            entry=entry,
            utterance=utterance,
            bearer_token=authorization.removeprefix("Bearer ").strip(),
            turn_number=turn_number,
        )
        started_at = time.perf_counter()
        try:
            agent_result = await asyncio.wait_for(
                self.agent_executor(
                    utterance=utterance,
                    uid=uid,
                    session_id=entry["session_id"],
                    authorization=authorization,
                    org_id=org_id,
                    guard=guard,
                ),
                timeout=self.timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError):
            logger.info(
                "voice turn complete uid=%s latency_ms=%d outcome=timeout",
                uid,
                int((time.perf_counter() - started_at) * 1000),
            )
            raise VoiceAssistantFailure(
                504,
                "That took too long. Please try again.",
                guard.trace,
                entry["session_id"],
            ) from None
        except Exception as exc:
            is_connection_failure = _is_mcp_connection_failure(exc)
            status_code = 502 if is_connection_failure else 500
            speech = "I couldn't reach LexProof just now." if is_connection_failure else "I couldn't complete that just now."
            logger.info(
                "voice turn complete uid=%s latency_ms=%d outcome=%s",
                uid,
                int((time.perf_counter() - started_at) * 1000),
                "mcp_connection_error" if is_connection_failure else "agent_error",
            )
            logger.warning("voice turn failed uid=%s category=%s", uid, "mcp_connection" if is_connection_failure else "agent")
            raise VoiceAssistantFailure(status_code, speech, guard.trace, entry["session_id"]) from None

        logger.info(
            "voice turn complete uid=%s latency_ms=%d outcome=ok",
            uid,
            int((time.perf_counter() - started_at) * 1000),
        )
        self.sessions.finish_turn(entry)
        result = _as_payload(agent_result)
        display_text = _redact_text(str(result.get("display_text") or utterance), guard.bearer_token)
        tool_speech = guard.tool_speech[-1] if guard.tool_speech else ""
        speech = guard.speech_override or tool_speech or str(result.get("speech") or display_text)
        speech = _short_speech(_redact_text(speech, guard.bearer_token))
        pending = entry.get("pending")
        awaiting = None
        if pending and pending.get("expires_at_epoch", 0) > int(time.time()):
            awaiting = {
                "short_code": pending["short_code"],
                "summary": pending["summary"],
                "expires_at": pending["expires_at"],
            }
        return {
            "session_id": entry["session_id"],
            "speech": speech,
            "display_text": display_text,
            "tool_trace": guard.trace,
            "awaiting_confirmation": awaiting,
        }
