"""Invoice ledger and receipt persistence.

Ledger writes and the matching obligation status update share one Firestore
transaction. Blocked tool calls are stored as receipts with an empty PayPal
payload so the evidence trail shows the denial.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import uuid4

from ...repositories.firestore import FirestoreRepository
from .evidence_record import write_payment_evidence
from .guard import GuardDecision, LedgerEntry
from .receipts import canonical_receipt, receipt_hash

INVOICES = "payment_invoices"
RECEIPTS = "payment_receipts"


def load_ledger(invoices: Any, obligations: Any, contract_id: str) -> dict[str, LedgerEntry]:
    obligation_status = {
        str(item.get("id")): str(item.get("status") or "")
        for item in obligations.stream()
        if item.get("contract_id") == contract_id
    }
    ledger: dict[str, LedgerEntry] = {}
    for item in invoices.stream():
        if item.get("contract_id") != contract_id:
            continue
        invoice_id = str(item.get("invoice_id") or item.get("id") or "")
        if not invoice_id:
            continue
        obligation_id = str(item.get("obligation_id") or "")
        ledger[invoice_id] = LedgerEntry(
            obligation_id=obligation_id,
            status=str(item.get("status") or ""),
            obligation_status=obligation_status.get(obligation_id, ""),
        )
    return ledger


def record_tool_result(
    *,
    invoices: Any,
    obligations: Any,
    receipts: Any,
    evidence: Any,
    passports: Any,
    org_id: str,
    contract_id: str,
    actor: str,
    tool: str,
    args: dict[str, Any],
    response: Any,
    decision: GuardDecision,
    receipt: dict[str, Any],
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Store the receipt and, when PayPal accepted a billing tool, move the ledger."""
    stamp = clock() if clock else datetime.now(timezone.utc).isoformat()
    stored_receipt = receipt
    if decision.decision != "allow":
        stored_receipt = canonical_receipt(tool, args, {}, decision, actor, contract_id)
    debug_id = _debug_id(response if decision.decision == "allow" else {})
    receipt_id = str(uuid4())
    evidence_id = write_payment_evidence(
        evidence=evidence,
        passports=passports,
        org_id=org_id,
        contract_id=contract_id,
        actor_id=actor,
        title=f"PayPal {tool} {decision.decision}",
        content={"receipt_hash": receipt_hash(stored_receipt), "tool": tool, "decision": decision.decision},
        source_id=receipt_id,
        now=lambda: stamp,
    )
    document = {
        **stored_receipt,
        "id": receipt_id,
        "org_id": org_id,
        "receipt_hash": receipt_hash(stored_receipt),
        "paypal_debug_id": debug_id,
        "evidence_id": evidence_id,
        "created_at": stamp,
    }
    receipts.set(receipt_id, document)
    if decision.decision == "allow" and _succeeded(response):
        _apply_success(
            invoices=invoices,
            obligations=obligations,
            org_id=org_id,
            contract_id=contract_id,
            tool=tool.strip().lower(),
            args=args,
            response=response,
            decision=decision,
            receipt_id=receipt_id,
            stamp=stamp,
        )
    return document


def _apply_success(
    *,
    invoices: Any,
    obligations: Any,
    org_id: str,
    contract_id: str,
    tool: str,
    args: dict[str, Any],
    response: Any,
    decision: GuardDecision,
    receipt_id: str,
    stamp: str,
) -> None:
    if tool == "create_invoice" and decision.matched_obligation_id:
        invoice_id = paypal_invoice_id(response)
        if not invoice_id:
            return
        obligation = obligations.get(decision.matched_obligation_id) or {}

        def apply(transaction: Any) -> None:
            if invoices.get(invoice_id, transaction=transaction):
                return
            invoices.set(
                invoice_id,
                {
                    "id": invoice_id,
                    "invoice_id": invoice_id,
                    "org_id": org_id,
                    "obligation_id": decision.matched_obligation_id,
                    "contract_id": contract_id,
                    "status": "DRAFT",
                    "currency": obligation.get("currency"),
                    "amount": obligation.get("amount"),
                    "created_receipt_id": receipt_id,
                    "payer_view_url": payer_view_url(response),
                    "created_at": stamp,
                    "updated_at": stamp,
                },
                transaction=transaction,
            )
            obligations.set(
                decision.matched_obligation_id,
                {"status": "INVOICED", "updated_at": stamp, "invoice_id": invoice_id},
                merge=True,
                transaction=transaction,
            )

        _transact(invoices, apply)
        return
    if tool == "send_invoice":
        invoice_id = str(args.get("invoice_id") or "").strip()
        entry = invoices.get(invoice_id) if invoice_id else None
        if not entry:
            return
        obligation_id = str(entry.get("obligation_id") or decision.matched_obligation_id or "")

        def apply_send(transaction: Any) -> None:
            sent = {"status": "SENT", "updated_at": stamp, "sent_receipt_id": receipt_id}
            view = payer_view_url(response)
            if view:
                sent["payer_view_url"] = view
            invoices.set(invoice_id, sent, merge=True, transaction=transaction)
            if obligation_id:
                obligations.set(obligation_id, {"status": "SENT", "updated_at": stamp}, merge=True, transaction=transaction)

        _transact(invoices, apply_send)
        return
    if tool in {"create_refund", "record_refund_for_invoice"}:
        _apply_refund(invoices, obligations, args, response, decision, receipt_id, stamp)


def apply_refund_outcome(
    invoices: Any,
    obligations: Any,
    args: dict[str, Any],
    response: Any,
    *,
    receipt_id: str,
    clock: Callable[[], str] | None = None,
) -> None:
    stamp = clock() if clock else datetime.now(timezone.utc).isoformat()
    _apply_refund(invoices, obligations, args, response, GuardDecision("allow", "approved payment action", None), receipt_id, stamp)


def _apply_refund(
    invoices: Any,
    obligations: Any,
    args: dict[str, Any],
    response: Any,
    decision: GuardDecision,
    receipt_id: str,
    stamp: str,
) -> None:
    invoice_id = str(args.get("invoice_id") or "").strip()
    entry = invoices.get(invoice_id) if invoice_id else None
    obligation_id = str((entry or {}).get("obligation_id") or decision.matched_obligation_id or "")
    obligation = obligations.get(obligation_id) if obligation_id else None
    if not obligation:
        return
    refunded_amount = _refund_amount(args, response)
    try:
        original = Decimal(str(obligation.get("amount") or "0").replace(",", ""))
    except (InvalidOperation, ValueError):
        original = Decimal(0)
    full = refunded_amount is None or (original > 0 and refunded_amount >= original)
    obligation_status = "REFUNDED" if full else "PARTIALLY_REFUNDED"
    ledger_status = "REFUNDED" if full else str((entry or {}).get("status") or "SENT")
    refund_id = paypal_refund_id(response)

    def apply(transaction: Any) -> None:
        if invoice_id and entry:
            invoices.set(
                invoice_id,
                {
                    "status": ledger_status,
                    "refunded_amount": format(refunded_amount, "f") if refunded_amount is not None else None,
                    "refund_id": refund_id,
                    "refund_receipt_id": receipt_id,
                    "updated_at": stamp,
                },
                merge=True,
                transaction=transaction,
            )
        obligations.set(
            obligation_id,
            {"status": obligation_status, "updated_at": stamp, "refund_id": refund_id},
            merge=True,
            transaction=transaction,
        )

    _transact(invoices, apply)


def payer_view_url(response: Any) -> str | None:
    """Payer link from a create/send invoice response. Sandbox hosts only."""
    if not isinstance(response, dict):
        return None
    links = response.get("links")
    candidates: list[str] = []
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue
            href = link.get("href")
            rel = str(link.get("rel") or "")
            if isinstance(href, str) and rel in {"payer-view", "payer_view"}:
                candidates.insert(0, href)
            elif isinstance(href, str):
                candidates.append(href)
    href = response.get("href")
    if isinstance(href, str):
        candidates.append(href)
    for candidate in candidates:
        parsed = urlparse(candidate.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "https" and (host == "sandbox.paypal.com" or host.endswith(".sandbox.paypal.com")):
            return candidate.strip()
    return None


def paypal_invoice_id(response: Any) -> str | None:
    found = _find_string(response, {"id", "invoice_id"})
    if found and found.upper().startswith("INV"):
        return found
    return found if found and "@" not in found and len(found) > 6 else None


def paypal_refund_id(response: Any) -> str | None:
    return _find_string(response, {"refund_id", "id"})


def _transact(repo: Any, callback: Callable[[Any], None]) -> None:
    if hasattr(repo, "run_transaction"):
        repo.run_transaction(callback)
        return
    callback(None)


def _succeeded(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    if response.get("blocked") or response.get("isError") or response.get("error"):
        return False
    return True


def _debug_id(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    for key in ("paypal_debug_id", "debug_id", "PayPal-Debug-Id"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _refund_amount(args: dict[str, Any], response: Any) -> Decimal | None:
    for source in (args, response if isinstance(response, dict) else {}):
        raw = source.get("amount") if isinstance(source, dict) else None
        if isinstance(raw, dict):
            raw = raw.get("value")
        if raw is None:
            continue
        try:
            amount = Decimal(str(raw).replace(",", ""))
        except (InvalidOperation, ValueError):
            continue
        if amount.is_finite() and amount >= 0:
            return amount
    return None


def _find_string(value: Any, keys: set[str]) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return _find_string(json.loads(text), keys)
            except json.JSONDecodeError:
                return None
        return None
    if isinstance(value, dict):
        for key in keys:
            found = value.get(key)
            if isinstance(found, str) and found.strip() and key != "id":
                return found.strip()
        if "id" in keys and isinstance(value.get("id"), str) and _looks_like_paypal_id(value["id"]):
            return value["id"].strip()
        for child in value.values():
            found = _find_string(child, keys)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_string(child, keys)
            if found:
                return found
    return None


def _looks_like_paypal_id(value: str) -> bool:
    text = value.strip()
    return bool(text) and " " not in text and "@" not in text and len(text) > 6


def default_invoices() -> FirestoreRepository:
    return FirestoreRepository(INVOICES)


def default_receipts() -> FirestoreRepository:
    return FirestoreRepository(RECEIPTS)
