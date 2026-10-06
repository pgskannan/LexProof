"""Public payment receipt chain. Emails are masked and PayPal payloads are omitted."""

from __future__ import annotations

import re
from typing import Any

from .checkpoint import CHAIN_VERSION, coverage, order_receipts
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
    checkpoints: Any | None = None,
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
    receipt_rows = order_receipts([item for item in receipts.stream() if item.get("contract_id") == contract_id])
    checkpoint_rows = [
        item for item in (checkpoints.stream() if checkpoints is not None else [])
        if item.get("contract_id") == contract_id and item.get("transaction_hash")
    ]
    covered_by = coverage(receipt_rows, checkpoint_rows)
    public_checkpoints = [
        {
            "checkpoint_id": item.get("id") or "",
            "count": item.get("count") or 0,
            "chain_head": item.get("chain_head") or "",
            "transaction_hash": item.get("transaction_hash") or "",
            "block_number": item.get("block_number"),
            "anchored_at": item.get("anchored_at"),
            "etherscan_url": f"https://sepolia.etherscan.io/tx/{item['transaction_hash']}",
        }
        for item in sorted(checkpoint_rows, key=lambda row: int(row.get("count") or 0))
    ]
    return {
        "passport_id": passport_id,
        "contract_id": contract_id,
        "mandate_hash": (stored or {}).get("mandate_hash") or "",
        "chain_version": CHAIN_VERSION,
        "checkpoints": public_checkpoints,
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
        "receipts": [_public_receipt(item, covered_by.get(str(item.get("id") or ""))) for item in receipt_rows],
    }


def public_receipt_canonical(item: dict[str, Any]) -> dict[str, Any]:
    """Canonical privacy-safe receipt displayed and hashed by public verification."""
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
    transport = item.get("transport")
    if isinstance(transport, str) and transport:
        canonical["transport"] = transport
    return canonical


def _public_receipt(item: dict[str, Any], checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    canonical = public_receipt_canonical(item)
    evidence_id = str(item.get("evidence_id") or "")
    transport = canonical.get("transport") or ("paypal_webhook" if item.get("source") == "paypal_webhook" else "mcp")
    anchored = bool(checkpoint and checkpoint.get("transaction_hash"))
    return {
        "tool": canonical["tool"],
        "decision": canonical["decision"],
        "time": canonical["time"],
        "receipt_hash": receipt_hash(canonical),
        "canonical": canonical_json(canonical),
        "evidence_id": evidence_id,
        "transport": transport,
        "anchor_status": "anchored" if anchored else "pending_checkpoint",
        "checkpoint_id": (checkpoint or {}).get("id"),
        "checkpoint_count": (checkpoint or {}).get("count"),
        "anchor_tx": (checkpoint or {}).get("transaction_hash"),
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
