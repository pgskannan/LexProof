"""Invoice ledger and receipt persistence.

Ledger writes and the matching obligation status update share one Firestore
transaction. Blocked tool calls are stored as receipts with an empty PayPal
payload so the evidence trail shows the denial.
"""

from __future__ import annotations

import json
import re
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
    document["paypal_invoice_id"] = _receipt_invoice_id(args, response, decision)
    document["amount"] = _quoted_amount(args, invoices, document["paypal_invoice_id"])
    receipts.set(receipt_id, document)
    confirmed = receipt.get("outcome") != "paypal_error"
    if decision.decision == "allow" and confirmed and _succeeded(response):
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
        if paypal_invoice_status(response) not in {"SENT", "UNPAID"}:
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
    """Buyer link. PayPal puts it on GET invoice at detail.metadata.recipient_view_url."""
    direct = _find_string(response, {"recipient_view_url", "payer_view_url"})
    if direct and _sandbox_url(direct):
        return direct
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
        if _sandbox_url(candidate):
            return candidate.strip()
    return None


def _sandbox_url(candidate: str) -> bool:
    parsed = urlparse(candidate.strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "sandbox.paypal.com" or host.endswith(".sandbox.paypal.com"))


_INVOICE_ID_RE = re.compile(r"INV2(?:-[A-Z0-9]{4}){4}")


def paypal_invoice_id(response: Any) -> str | None:
    found = _find_string(response, {"id", "invoice_id"})
    if found and found.upper().startswith("INV"):
        return found
    # PayPal's create-draft-invoice returns only a link
    # ({"rel": "self", "href": ".../v2/invoicing/invoices/INV2-..."}), so look for
    # the id anywhere in the payload before falling back to a generic id.
    try:
        blob = json.dumps(response, default=str)
    except (TypeError, ValueError):
        blob = str(response)
    match = _INVOICE_ID_RE.search(blob)
    if match:
        return match.group(0)
    return found if found and "@" not in found and len(found) > 6 else None


def paypal_refund_id(response: Any) -> str | None:
    return _find_string(response, {"refund_id", "id"})


def _transact(repo: Any, callback: Callable[[Any], None]) -> None:
    if hasattr(repo, "run_transaction"):
        repo.run_transaction(callback)
        return
    callback(None)


_PAYPAL_ERROR_NAMES = frozenset(
    {
        "UNPROCESSABLE_ENTITY",
        "INVALID_REQUEST",
        "RESOURCE_NOT_FOUND",
        "NOT_AUTHORIZED",
        "PERMISSION_DENIED",
        "INTERNAL_SERVER_ERROR",
        "VALIDATION_ERROR",
    }
)
_INVOICE_STATUSES = frozenset(
    {
        "DRAFT",
        "SENT",
        "UNPAID",
        "SCHEDULED",
        "PAID",
        "MARKED_AS_PAID",
        "CANCELLED",
        "REFUNDED",
        "PARTIALLY_PAID",
        "PARTIALLY_REFUNDED",
        "PAYMENT_PENDING",
    }
)


def paypal_failure(response: Any) -> str | None:
    """PayPal issue text when a response is a failure, including MCP content JSON. None on success."""
    return _failure(response)


def paypal_invoice_status(response: Any) -> str | None:
    return _invoice_status(response)


def _succeeded(response: Any) -> bool:
    return paypal_failure(response) is None and isinstance(response, dict)


async def confirm_tool_result(
    tool: str,
    args: dict[str, Any],
    response: Any,
    fetch: Callable[[str, dict[str, Any]], Any],
) -> tuple[Any, str | None]:
    """Confirm a write with PayPal. The issue string is None only when PayPal's state matches the write."""
    name = tool.strip().lower()
    failure = paypal_failure(response)
    if name == "create_invoice":
        if failure:
            return response, failure
        if not paypal_invoice_id(response):
            return response, "PayPal did not return an invoice id"
        return response, None
    if name == "send_invoice":
        if failure:
            return response, failure
        invoice_id = str(args.get("invoice_id") or "").strip()
        fetched = await fetch("get_invoice", {"invoice_id": invoice_id})
        return _confirmed_send(response, fetched)
    if name in {"create_refund", "record_refund_for_invoice"}:
        if failure:
            return response, failure
        return response, None
    return response, None


def _confirmed_send(response: Any, fetched: Any) -> tuple[Any, str | None]:
    status = paypal_invoice_status(fetched)
    view = payer_view_url(fetched)
    merged = dict(response) if isinstance(response, dict) else {"send_response": response}
    merged["get_invoice"] = fetched
    if status:
        merged["status"] = status
    if view:
        merged["payer_view_url"] = view
    if status in {"SENT", "UNPAID"}:
        return merged, None
    fetched_issue = paypal_failure(fetched)
    if fetched_issue:
        return merged, fetched_issue
    return merged, f"PayPal invoice status is {status or 'UNKNOWN'}"


def _failure(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return _failure(json.loads(text))
            except json.JSONDecodeError:
                return None
        return None
    if isinstance(value, list):
        for child in value:
            found = _failure(child)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if isinstance(name, str) and name in _PAYPAL_ERROR_NAMES:
        return _issue_text(value) or name
    details = value.get("details")
    if isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict) and isinstance(detail.get("issue"), str) and detail["issue"].strip():
                return detail["issue"].strip()
    for key in ("status_code", "statusCode", "http_status"):
        code = _http_status(value.get(key))
        if code is not None and code >= 400:
            return _issue_text(value) or f"HTTP {code}"
    status_code = _http_status(value.get("status"))
    if status_code is not None and status_code >= 400:
        return _issue_text(value) or f"HTTP {status_code}"
    flagged = value.get("isError") is True or value.get("blocked") is True or bool(value.get("error"))
    for child in value.values():
        found = _failure(child)
        if found:
            return found
    if flagged:
        error = value.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        return "PayPal error"
    return None


def _issue_text(value: dict[str, Any]) -> str | None:
    details = value.get("details")
    if isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict) and isinstance(detail.get("issue"), str) and detail["issue"].strip():
                return detail["issue"].strip()
    return None


def _http_status(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _invoice_status(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return _invoice_status(json.loads(text))
            except json.JSONDecodeError:
                return None
        return None
    if isinstance(value, dict):
        status = value.get("status")
        if isinstance(status, str) and status.strip().upper() in _INVOICE_STATUSES:
            return status.strip().upper()
        for child in value.values():
            found = _invoice_status(child)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _invoice_status(child)
            if found:
                return found
    return None


def _receipt_invoice_id(args: dict[str, Any], response: Any, decision: GuardDecision) -> str | None:
    if decision.decision != "allow":
        return None
    found = paypal_invoice_id(response)
    if found:
        return found
    invoice_id = args.get("invoice_id") if isinstance(args, dict) else None
    if isinstance(invoice_id, str) and invoice_id.strip():
        return invoice_id.strip()
    return None


def _quoted_amount(args: dict[str, Any], invoices: Any, invoice_id: str | None) -> str | None:
    items = args.get("items") if isinstance(args, dict) else None
    if isinstance(items, list):
        total = Decimal(0)
        saw = False
        try:
            for item in items:
                if not isinstance(item, dict):
                    continue
                unit = item.get("unit_amount")
                if not isinstance(unit, dict) or unit.get("value") is None:
                    continue
                quantity = Decimal(str(item.get("quantity") or "1").replace(",", ""))
                total += quantity * Decimal(str(unit.get("value")).replace(",", ""))
                saw = True
            if saw:
                return f"{total.quantize(Decimal('0.01')):,.2f}"
        except (InvalidOperation, ValueError):
            saw = False
    if invoice_id:
        row = invoices.get(invoice_id) or {}
        amount = row.get("amount")
        if amount is not None and str(amount).strip():
            return str(amount)
    return None


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
