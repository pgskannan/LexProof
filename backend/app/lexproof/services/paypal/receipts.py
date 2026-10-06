"""Canonical PayPal tool receipts.

Receipts keep the decision and the email addresses needed to audit a payment.
Tokens and other PII are removed before the hash is computed.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from .guard import GuardDecision

_SECRET_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)
_PII_EXACT = {
    "phone",
    "phone_number",
    "mobile",
    "telephone",
    "address",
    "street",
    "city",
    "state",
    "postal_code",
    "zip",
    "zip_code",
    "ssn",
    "social_security_number",
    "name",
    "first_name",
    "last_name",
    "full_name",
    "given_name",
    "surname",
    "dob",
    "date_of_birth",
    "birth_date",
    "shipping_address",
    "billing_address",
}
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*")
_PAYPAL_ACCESS_TOKEN = re.compile(r"\bA21[A-Za-z0-9_\-]{20,}\b")


def canonical_json(value: Any) -> str:
    """JSON with sorted keys and no insignificant whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def receipt_hash(receipt: dict[str, Any]) -> str:
    """SHA-256 hex digest of the canonical receipt JSON."""
    return hashlib.sha256(canonical_json(receipt).encode("utf-8")).hexdigest()


def canonical_receipt(
    tool: str,
    args: Any,
    response: Any,
    decision: GuardDecision | dict[str, Any] | str,
    actor: str,
    contract_id: str,
) -> dict[str, Any]:
    """Build the audit receipt for one tool call."""
    decision_name, reason, matched = _decision_parts(decision)
    return {
        "actor": _redact_text(actor),
        "args": strip_sensitive(args),
        "contract_id": _redact_text(contract_id),
        "decision": decision_name,
        "matched_obligation_id": matched,
        "reason": reason,
        "response": strip_sensitive(response),
        "tool": tool,
    }


def strip_sensitive(value: Any) -> Any:
    """Drop token fields and PII other than email addresses."""
    prepared = _jsonable(value)
    return _strip(prepared)


def _decision_parts(decision: GuardDecision | dict[str, Any] | str) -> tuple[str, str | None, str | None]:
    if isinstance(decision, GuardDecision):
        return decision.decision, decision.reason, decision.matched_obligation_id
    if isinstance(decision, dict):
        return (
            str(decision.get("decision")),
            decision.get("reason") if isinstance(decision.get("reason"), str) else None,
            decision.get("matched_obligation_id") if isinstance(decision.get("matched_obligation_id"), str) else None,
        )
    return str(decision), None, None


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return str(value)


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _drop_key(key):
                continue
            cleaned[key] = _strip(item)
        return cleaned
    if isinstance(value, list):
        return [_strip(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _drop_key(key: str) -> bool:
    lowered = key.lower()
    if "email" in lowered:
        return False
    if any(fragment in lowered for fragment in _SECRET_FRAGMENTS):
        return True
    if lowered in _PII_EXACT:
        return True
    if lowered.endswith("_name") or "address" in lowered or "phone" in lowered:
        return True
    return False


def _redact_text(value: str) -> str:
    redacted = _BEARER.sub("[redacted]", value)
    return _PAYPAL_ACCESS_TOKEN.sub("[redacted]", redacted)
