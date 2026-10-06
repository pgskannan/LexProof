"""Public payment receipt chain. Emails are masked and PayPal payloads are omitted."""

from __future__ import annotations

import re
from typing import Any

from .receipts import canonical_json, receipt_hash

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def mask_email(value: str) -> str:
    """Keep the first character and the domain: s***@example.com."""
    local, separator, domain = value.partition("@")
    if not separator or not local or not domain:
        return value
    return f"{local[0]}***@{domain}"


def mask_emails(value: Any) -> Any:
    if isinstance(value, str):
        return mask_email(value) if _EMAIL.match(value) else value
    if isinstance(value, list):
        return [mask_emails(item) for item in value]
    if isinstance(value, dict):
        return {str(key): mask_emails(item) for key, item in value.items()}
    return value


def public_payment_chain(
    passport_id: str,
    *,
    passports: Any,
    obligations: Any,
    receipts: Any,
    settings: Any,
    anchors: Any | None = None,
) -> dict[str, Any] | None:
    """Obligations, mandate hash, and ordered receipts for one passport."""
    passport = _passport(passports, passport_id)
    if passport is None:
        return None
    contract_id = str(passport.get("contract_id") or "")
    if not contract_id:
        return None
    stored = settings.get(contract_id) if settings is not None else None
    rows = [item for item in obligations.stream() if item.get("contract_id") == contract_id]
    rows.sort(key=lambda item: str(item.get("id") or ""))
    receipt_rows = [item for item in receipts.stream() if item.get("contract_id") == contract_id]
    receipt_rows.sort(key=lambda item: str(item.get("created_at") or ""))
    return {
        "passport_id": passport_id,
        "contract_id": contract_id,
        "mandate_hash": (stored or {}).get("mandate_hash") or "",
        "obligations": [
            {
                "label": item.get("label") or "",
                "amount": item.get("amount") or "",
                "currency": item.get("currency") or "",
                "status": item.get("status") or "",
                "clause_ref": item.get("clause_ref") or "",
            }
            for item in rows
        ],
        "receipts": [_public_receipt(item, anchors) for item in receipt_rows],
    }


def _public_receipt(item: dict[str, Any], anchors: Any | None) -> dict[str, Any]:
    canonical = {
        "actor": mask_emails(item.get("actor") or ""),
        "amount": item.get("amount") or "",
        "contract_id": item.get("contract_id") or "",
        "currency": item.get("currency") or "",
        "decision": item.get("decision") or "",
        "event_id": item.get("event_id") or "",
        "reason": item.get("reason") or "",
        "resource_id": item.get("resource_id") or item.get("invoice_id") or "",
        "source": item.get("source") or "paypal_tool",
        "time": item.get("created_at") or item.get("time") or "",
        "tool": item.get("tool") or "",
    }
    evidence_id = str(item.get("evidence_id") or "")
    anchor = anchors.get(evidence_id) if anchors is not None and evidence_id else None
    anchored = bool(anchor and (anchor.get("transaction_hash") or anchor.get("anchored_at")))
    return {
        "tool": canonical["tool"],
        "decision": canonical["decision"],
        "time": canonical["time"],
        "receipt_hash": receipt_hash(canonical),
        "canonical": canonical_json(canonical),
        "evidence_id": evidence_id,
        "anchor_status": "anchored" if anchored else "not_anchored",
    }


def _passport(passports: Any, passport_id: str) -> dict[str, Any] | None:
    direct = passports.get(passport_id)
    if direct:
        return direct
    for item in passports.stream():
        if item.get("passport_id") == passport_id or item.get("id") == passport_id:
            return item
    prefix = "payment-"
    if passport_id.startswith(prefix) and passport_id[len(prefix) :]:
        return {"id": passport_id, "passport_id": passport_id, "contract_id": passport_id[len(prefix) :]}
    return None
