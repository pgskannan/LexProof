"""Prepare and explicitly confirm approval actions over the REST API."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import secrets
import string
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.server import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel

from ..config import get_settings
from ..services.auth import read_only_uids
from .client import call_api
from .org import resolve_org_id
from .workflow_titles import resolve_workflow_contract_name, workflow_structured_subject, workflow_subject
from .spoken_names import amount_in_words, spoken_contract_name, spoken_payment_contract

logger = logging.getLogger(__name__)
TOKEN_TTL_SECONDS = 300
_short_codes: dict[tuple[str, str], tuple[str, int]] = {}
_consumed_tokens: dict[str, int] = {}
_in_flight_tokens: set[str] = set()


class PreparedDecision(BaseModel):
    summary: str
    consequences: str
    confirmation_code: str
    confirmation_token: str
    expires_at: str
    speech: str


class ConfirmedDecision(BaseModel):
    success: bool
    summary: str
    speech: str


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret() -> bytes:
    value = get_settings().mcp_confirm_secret.get_secret_value()
    if not value:
        raise ToolError("Decision confirmation is not configured on this server.")
    return value.encode("utf-8")


def _signature(payload: bytes) -> str:
    return _b64(hmac.new(_secret(), payload, hashlib.sha256).digest())


def _token(payload: dict[str, Any]) -> str:
    encoded = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_signature(encoded.encode('ascii'))}"


def _read_token(token: str) -> dict[str, Any]:
    try:
        encoded, signature = token.split(".", 1)
        expected = _signature(encoded.encode("ascii"))
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(_unb64(encoded))
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise ToolError("Confirmation code is invalid.") from None


def _state_digest(kind: str, item: dict[str, Any]) -> str:
    if kind == "workflow":
        state = {
            key: item.get(key)
            for key in ("instance_id", "org_id", "definition_id", "definition_version", "current_state", "status", "updated_at", "updated_by")
        }
    else:
        state = {
            key: item.get(key)
            for key in (
                "id", "org_id", "contract_id", "status", "updated_at", "edited_by", "approved_by",
                "amount", "currency", "due_date", "payer_email", "needs_review_reason", "label",
            )
        }
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(canonical).hexdigest()


_ACTION_VERBS = {
    "approve": ("approve", "approved"),
    "reject": ("reject", "rejected"),
    "request_changes": ("request changes", "requested changes"),
    "submit": ("submit", "submitted"),
}


def action_verbs(action_id: str, action_label: str = "") -> tuple[str, str, str | None]:
    """Return infinitive, past tense, and any object phrase for an action."""
    normalized_id = action_id.casefold().replace("-", "_")
    normalized_label = " ".join(action_label.strip().split())
    label_words = normalized_label.split()
    normalized_first = label_words[0].casefold().replace("-", "_") if label_words else ""
    normalized_first_pair = " ".join(label_words[:2]).casefold().replace("-", " ")

    if normalized_id.startswith("request_changes") or normalized_first_pair == "request changes":
        return "request changes to", "requested changes to", None
    for action, verbs in _ACTION_VERBS.items():
        if action == "request_changes":
            continue
        if normalized_id == action or normalized_id.startswith(f"{action}_") or normalized_first == action:
            remainder = " ".join(label_words[1:]).strip() if normalized_first == action else None
            if action == "submit" and remainder and remainder.casefold() in {"for review", "for approval"}:
                remainder = None
            return (*verbs, remainder or None)
    fallback_label = normalized_label or action_id.replace("_", " ").replace("-", " ")
    fallback_label = fallback_label[:1].lower() + fallback_label[1:]
    return "complete", "completed", fallback_label


def payment_speech_subject(obligation: dict[str, Any], contract_name: str) -> tuple[str, str]:
    name = spoken_payment_contract(obligation, contract_name)
    return f"{amount_in_words(obligation.get('amount'), obligation.get('currency'))} for the {name} contract", name


def payment_structured_summary(action_id: str, obligation: dict[str, Any], contract_name: str) -> str:
    action = action_id.replace("_", " ").replace("-", " ").capitalize()
    label = str(obligation.get("label") or obligation.get("trigger_text") or "payment").strip()
    amount = str(obligation.get("amount") or "0").strip()
    currency = str(obligation.get("currency") or "USD").upper()
    return f"{action} {amount} {currency} {label} payment for {contract_name}"


def payment_decision_phrases(
    action_id: str,
    obligation: dict[str, Any],
    contract_name: str,
) -> tuple[str, str, str, str]:
    infinitive, past_tense, _ = action_verbs(action_id, action_id)
    payment_subject, _ = payment_speech_subject(obligation, contract_name)
    summary = payment_structured_summary(action_id, obligation, contract_name)
    speech = f"Ready to {infinitive} {payment_subject}. Say confirm to proceed. Nothing has changed yet."
    return infinitive, past_tense, summary, speech


def confirmed_payment_speech(action_id: str, obligation: dict[str, Any], contract_name: str) -> tuple[str, str]:
    _infinitive, past_tense, _ = action_verbs(action_id, action_id)
    payment_subject, _ = payment_speech_subject(obligation, contract_name)
    summary = payment_structured_summary(action_id, obligation, contract_name)
    speech = f"Done. You {past_tense} {payment_subject}. It's recorded in the audit log."
    return summary, speech


def workflow_decision_phrases(
    action_id: str,
    action_label: str,
    instance: dict[str, Any],
    definition: dict[str, Any],
    contract_name: str | None,
) -> tuple[str, str, str, str]:
    infinitive, past_tense, action_object = action_verbs(action_id, action_label)
    if action_object:
        spoken_subject = action_object if infinitive == "complete" else f"the {action_object}"
        subject = spoken_subject
        if contract_name:
            subject += f" for the {contract_name}"
            spoken_subject += f" for the {spoken_contract_name(contract_name)}"
    else:
        subject = workflow_structured_subject(instance, definition, contract_name)
        spoken_subject = workflow_subject(instance, definition, contract_name)
    return (
        infinitive,
        past_tense,
        subject,
        f"Done. You {past_tense} {spoken_subject}. It's recorded in the workflow history.",
    )


def prepared_decision_speech(infinitive: str, subject: str, speech_subject: str | None = None) -> str:
    return f"Ready to {infinitive} {speech_subject or subject}. Say confirm to proceed. Nothing has changed yet."


async def _roles(org_id: str) -> tuple[str, list[str]]:
    token = get_access_token()
    uid = (token.subject if token else None) or str((token.claims if token else {}).get("uid") or "")
    profile = await call_api("GET", "/api/me", org_id=org_id)
    for membership in profile.get("orgs") or []:
        if membership.get("org_id") == org_id and membership.get("member_status") == "active":
            return uid, [str(role) for role in membership.get("roles") or []]
    raise ToolError("You are not an active member of this organization.")


async def _contracts(org_id: str) -> list[dict[str, Any]]:
    return await call_api("GET", "/api/contracts", org_id=org_id)


async def _load_payment_obligation(org_id: str, obligation_id: str) -> tuple[dict[str, Any], str]:
    contracts = await _contracts(org_id)
    for contract in contracts[:25]:
        contract_id = str(contract.get("contract_id") or "")
        if not contract_id:
            continue
        view = await call_api(
            "GET",
            f"/api/contracts/{quote(contract_id, safe='')}/payments",
            org_id=org_id,
        )
        for item in view.get("obligations") or []:
            if str(item.get("id") or "") == obligation_id:
                return item, str(contract.get("name") or "Untitled contract")
    raise ToolError("The payment obligation was not found in this organization.")


async def _load_workflow(org_id: str, item_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    instance = await call_api(
        "GET",
        f"/api/orgs/{quote(org_id, safe='')}/workflow-instances/{quote(item_id, safe='')}",
        org_id=org_id,
    )
    definition = await call_api(
        "GET",
        f"/api/orgs/{quote(org_id, safe='')}/workflow-definitions/{quote(str(instance.get('definition_id') or ''), safe='')}",
        org_id=org_id,
    )
    return instance, definition


def _short_code(token: str, attempt: int = 0) -> str:
    digest = hashlib.sha256(f"{attempt}:{token}".encode("ascii")).digest()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    value = int.from_bytes(digest[:5], "big")
    chars = []
    for _ in range(6):
        chars.append(alphabet[value & 31])
        value >>= 5
    return "".join(chars)


def _register_short_code(uid: str, token: str, expires_at: int) -> str:
    now = int(time.time())
    for key, (_, expiry) in list(_short_codes.items()):
        if expiry <= now:
            _short_codes.pop(key, None)
    for token_id, expiry in list(_consumed_tokens.items()):
        if expiry <= now:
            _consumed_tokens.pop(token_id, None)
    attempt = 0
    code = _short_code(token, attempt)
    while (uid, code) in _short_codes and _short_codes[(uid, code)][0] != token:
        attempt += 1
        code = _short_code(token, attempt)
    _short_codes[(uid, code)] = (token, expires_at)
    return code


def _decision_log(tool: str, uid: str, org_id: str, kind: str, item_id: str, action_id: str, outcome: str, started: float) -> None:
    logger.info(
        "MCP decision tool=%s uid=%s org_id=%s kind=%s item_id=%s action_id=%s outcome=%s latency_ms=%.1f",
        tool, uid, org_id, kind, item_id, action_id, outcome, (time.perf_counter() - started) * 1000,
    )


def register_decision_tools(server: MCPServer, read_annotations: ToolAnnotations) -> None:
    confirm_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )

    async def prepare_decision(
        kind: str,
        item_id: str,
        action_id: str,
        comment: str | None = None,
        org_id: str | None = None,
        context: Context | None = None,
    ) -> PreparedDecision:
        selected_org = await resolve_org_id(org_id, context)
        uid, roles = await _roles(selected_org)
        started = time.perf_counter()
        snapshot: dict[str, Any]
        summary: str
        consequences: str
        infinitive: str
        past_tense: str
        subject: str
        if kind == "workflow":
            instance, definition = await _load_workflow(selected_org, item_id)
            if instance.get("status") != "in_progress":
                raise ToolError("This workflow is no longer awaiting approval.")
            transition = next((
                item for item in definition.get("transitions") or []
                if item.get("id") == action_id and item.get("from_state") == instance.get("current_state")
            ), None)
            if not transition:
                raise ToolError("That action is not currently legal for this workflow.")
            allowed = set(transition.get("allowed_roles") or [])
            if allowed and not allowed.intersection(roles):
                raise ToolError("Your organization roles cannot perform that workflow action.")
            if any(instance.get(field) == uid for field in transition.get("requires_not_actor") or []):
                raise ToolError("You cannot approve an item you created under its separation-of-duties rule.")
            action_name = str(transition.get("action_name") or action_id)
            contract_name = await resolve_workflow_contract_name(instance, selected_org)
            infinitive, _past_tense, subject, _confirmation_speech = workflow_decision_phrases(
                action_id, action_name, instance, definition, contract_name
            )
            summary = f"{infinitive.capitalize()} {subject}"
            target_state = str(transition.get("to_state") or "the next state")
            consequences = f"The workflow will move to {target_state}, and the transition will be recorded in its history."
            snapshot = instance
        elif kind == "payment_obligation":
            obligation, contract_name = await _load_payment_obligation(selected_org, item_id)
            if action_id not in {"approve", "reject"}:
                raise ToolError("Payment action must be approve or reject.")
            if not set(roles).intersection({"approver", "admin"}):
                raise ToolError("Your organization roles cannot approve payment obligations.")
            if str(obligation.get("status") or "").upper() not in {"EXTRACTED", "PENDING_APPROVAL", "NEEDS_REVIEW"}:
                raise ToolError("This payment obligation is no longer awaiting approval.")
            if obligation.get("edited_by") and str(obligation.get("edited_by")) == uid:
                raise ToolError("Approver must be different from the last editor.")
            if action_id == "approve" and not str(obligation.get("payer_email") or "").strip():
                raise ToolError("Approving requires a payer email on the obligation.")
            if action_id == "approve" and obligation.get("needs_review_reason") and not obligation.get("edited_by"):
                raise ToolError("This obligation needs review before approval.")
            infinitive, _past_tense, summary, speech = payment_decision_phrases(action_id, obligation, contract_name)
            consequences = "The payment obligation status and approved mandate will be updated and recorded in the audit log."
            snapshot = obligation
        else:
            raise ToolError("kind must be workflow or payment_obligation.")

        now = int(time.time())
        expires_at = now + TOKEN_TTL_SECONDS
        payload = {
            "uid": uid,
            "org_id": selected_org,
            "kind": kind,
            "item_id": item_id,
            "action_id": action_id,
            "comment": comment,
            "comment_sha256": hashlib.sha256((comment or "").encode("utf-8")).hexdigest(),
            "state_sha256": _state_digest(kind, snapshot),
            "exp": expires_at,
            "jti": secrets.token_urlsafe(16),
        }
        signed = _token(payload)
        code = _register_short_code(uid, signed, expires_at)
        _decision_log("prepare_decision", uid, selected_org, kind, item_id, action_id, "prepared", started)
        return PreparedDecision(
            summary=summary,
            consequences=consequences,
            confirmation_code=code,
            confirmation_token=signed,
            expires_at=datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
            speech=speech if kind == "payment_obligation" else prepared_decision_speech(infinitive, subject),
        )

    async def confirm_decision(
        confirmation_code: str,
        context: Context | None = None,
    ) -> ConfirmedDecision:
        token_context = get_access_token()
        uid = (token_context.subject if token_context else None) or str((token_context.claims if token_context else {}).get("uid") or "")
        started = time.perf_counter()
        supplied = confirmation_code.strip()
        if "." not in supplied:
            cached = _short_codes.get((uid, supplied.upper()))
            if not cached or cached[1] <= int(time.time()):
                raise ToolError("Confirmation code is invalid or expired. Prepare the decision again.")
            token = cached[0]
        else:
            token = supplied
        payload = _read_token(token)
        org_id = str(payload.get("org_id") or "")
        kind = str(payload.get("kind") or "")
        item_id = str(payload.get("item_id") or "")
        action_id = str(payload.get("action_id") or "")
        token_id = str(payload.get("jti") or "")
        if payload.get("uid") != uid:
            _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "wrong_user", started)
            raise ToolError("This confirmation belongs to another user.")
        if int(payload.get("exp") or 0) <= int(time.time()):
            _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "expired", started)
            raise ToolError("Confirmation expired. Prepare the decision again.")
        expected_comment_hash = hashlib.sha256(str(payload.get("comment") or "").encode("utf-8")).hexdigest()
        if not hmac.compare_digest(expected_comment_hash, str(payload.get("comment_sha256") or "")):
            _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "invalid_comment_hash", started)
            raise ToolError("Confirmation is invalid. Prepare the decision again.")
        if token_id in _consumed_tokens or token_id in _in_flight_tokens:
            _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "replayed", started)
            raise ToolError("This confirmation has already been used.")
        _in_flight_tokens.add(token_id)

        try:
            payment_contract_name = ""
            workflow_definition: dict[str, Any] = {}
            if kind == "workflow":
                instance, workflow_definition = await _load_workflow(org_id, item_id)
                current = instance
            elif kind == "payment_obligation":
                current, payment_contract_name = await _load_payment_obligation(org_id, item_id)
            else:
                raise ToolError("Confirmation kind is invalid.")
            if not hmac.compare_digest(_state_digest(kind, current), str(payload.get("state_sha256") or "")):
                _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "state_changed", started)
                raise ToolError("This item changed since you asked. Please prepare the decision again.")

            if kind == "workflow":
                result = await call_api(
                    "POST",
                    f"/api/orgs/{quote(org_id, safe='')}/workflow-instances/{quote(item_id, safe='')}/transitions",
                    json={"transition_id": action_id, "comment": payload.get("comment")},
                    org_id=org_id,
                )
            else:
                suffix = "approve" if action_id == "approve" else "reject"
                result = await call_api(
                    "POST",
                    f"/api/payment-obligations/{quote(item_id, safe='')}:{suffix}",
                    org_id=org_id,
                )
            _consumed_tokens[token_id] = int(payload["exp"])
            if kind == "payment_obligation":
                summary, speech = confirmed_payment_speech(action_id, current, payment_contract_name)
            else:
                transition = next((entry for entry in workflow_definition.get("transitions", []) if entry.get("id") == action_id), {})
                action_label = str(transition.get("action_name") or action_id)
                contract_name = await resolve_workflow_contract_name(current, org_id)
                _infinitive, decision_verb, subject, speech = workflow_decision_phrases(
                    action_id,
                    action_label,
                    current,
                    workflow_definition,
                    contract_name,
                )
                summary = f"{decision_verb.capitalize()} {subject}"
            _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "confirmed", started)
            return ConfirmedDecision(success=True, summary=summary, speech=speech)
        except ToolError as error:
            if uid in read_only_uids() and "access to this organization" in str(error).casefold():
                _consumed_tokens[token_id] = int(payload["exp"])
                _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "read_only", started)
                return ConfirmedDecision(
                    success=False,
                    summary="No change was made because this account is read-only.",
                    speech="This is a read-only demo account, so I can't make changes. In a live workspace this would be approved now.",
                )
            raise
        finally:
            _in_flight_tokens.discard(token_id)

    async def logged_prepare_decision(
        kind: str,
        item_id: str,
        action_id: str,
        comment: str | None = None,
        org_id: str | None = None,
        context: Context | None = None,
    ) -> PreparedDecision:
        started = time.perf_counter()
        try:
            return await prepare_decision(kind, item_id, action_id, comment, org_id, context)
        except ToolError:
            token = get_access_token()
            uid = (token.subject if token else None) or str((token.claims if token else {}).get("uid") or "unknown")
            resolved_org = org_id or ((context.headers or {}).get("X-Org-Id") if context else None) or "unresolved"
            _decision_log("prepare_decision", uid, resolved_org, kind, item_id, action_id, "error", started)
            raise

    async def logged_confirm_decision(
        confirmation_code: str,
        context: Context | None = None,
    ) -> ConfirmedDecision:
        started = time.perf_counter()
        token = get_access_token()
        uid = (token.subject if token else None) or str((token.claims if token else {}).get("uid") or "unknown")
        org_id = kind = item_id = action_id = "unknown"
        supplied = confirmation_code.strip()
        try:
            cached = _short_codes.get((uid, supplied.upper())) if "." not in supplied else None
            signed = cached[0] if cached else supplied
            payload, _, _ = signed.partition(".")
            decoded = json.loads(_unb64(payload))
            org_id = str(decoded.get("org_id") or org_id)
            kind = str(decoded.get("kind") or kind)
            item_id = str(decoded.get("item_id") or item_id)
            action_id = str(decoded.get("action_id") or action_id)
        except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            pass
        try:
            return await confirm_decision(confirmation_code, context)
        except ToolError:
            _decision_log("confirm_decision", uid, org_id, kind, item_id, action_id, "error", started)
            raise

    server.add_tool(
        logged_prepare_decision,
        name="prepare_decision",
        title="Prepare an approval decision",
        description="Re-check a currently legal workflow or payment action and prepare a five-minute confirmation. This does not change data.",
        annotations=read_annotations,
        structured_output=True,
    )
    server.add_tool(
        logged_confirm_decision,
        name="confirm_decision",
        title="Confirm an approval decision",
        description="Execute a prepared approval only after the user explicitly confirms in the current conversation. Read the prepared summary aloud first.",
        annotations=confirm_annotations,
        structured_output=True,
    )