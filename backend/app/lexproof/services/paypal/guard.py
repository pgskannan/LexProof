"""Pure PaymentGuard for PayPal MCP tools.

Unknown tools are writes and are denied. Billing is allowed only when the
arguments match one approved obligation. Money leaving the merchant requires
an approval id bound to the exact tool name and canonical arguments.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

# Hosted sandbox tools/list on 2026-10-05, SSE https://mcp.sandbox.paypal.com/sse.
# READ (list_*, get_*, show_*): get_recurring_series, list_invoices, get_invoice,
# list_products, show_product_details, list_subscription_plans,
# show_subscription_plan_details, show_subscription_details, get_shipment_tracking,
# get_order, list_disputes, get_dispute, list_transactions, get_refund,
# get_merchant_insights.
# Denied as OTHER_WRITE until added here: search_invoicing, update_invoicing,
# delete_invoice, delete_recurring_series, pay_order, record_payment_for_invoice,
# create_product, update_product, create_subscription, update_subscription,
# create_shipment_tracking, update_shipment_tracking, generate_invoice_qr_code,
# generate_invoice_number, and the other create_/update_/activate_/setup_ tools.
# cancel_* is money-out even when the specific name is not listed below.
PAYPAL_TOOL_CLASSES: dict[str, tuple[str, ...]] = {
    "READ_PREFIXES": ("list_", "get_", "show_"),
    "BILLING": (
        "create_invoice",
        "send_invoice",
        "send_invoice_reminder",
        "create_order",
    ),
    "MONEY_OUT": (
        "create_refund",
        "record_refund_for_invoice",
        "accept_dispute_claim",
        "cancel_subscription",
    ),
    "MONEY_OUT_PREFIXES": ("cancel_",),
}

_EXTRA_RECIPIENT_KEYS = (
    "cc_emails",
    "cc",
    "bcc",
    "additional_recipients",
    "secondary_recipients",
    "extra_recipients",
)
_RECIPIENT_KEYS = ("recipient_email", "payer_email", "email", "recipient", "primary_recipients", "recipients")
_AMOUNT_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")


class ToolClass(Enum):
    READ = "READ"
    BILLING = "BILLING"
    MONEY_OUT = "MONEY_OUT"
    OTHER_WRITE = "OTHER_WRITE"


@dataclass(frozen=True)
class ApprovedObligation:
    """A contract obligation the guard may bill against."""

    id: str
    currency: str
    amount: Decimal | str | int
    payer_email: str
    status: str


@dataclass(frozen=True)
class GuardDecision:
    decision: str
    reason: str
    matched_obligation_id: str | None = None


def classify(tool_name: str) -> ToolClass:
    """Classify a tool. Anything unrecognized is ``OTHER_WRITE``."""
    if not isinstance(tool_name, str):
        return ToolClass.OTHER_WRITE
    name = tool_name.strip().lower()
    if name in PAYPAL_TOOL_CLASSES["BILLING"]:
        return ToolClass.BILLING
    if name in PAYPAL_TOOL_CLASSES["MONEY_OUT"]:
        return ToolClass.MONEY_OUT
    if name.startswith(PAYPAL_TOOL_CLASSES["MONEY_OUT_PREFIXES"]):
        return ToolClass.MONEY_OUT
    if name.startswith(PAYPAL_TOOL_CLASSES["READ_PREFIXES"]):
        return ToolClass.READ
    return ToolClass.OTHER_WRITE


def decide(
    tool_name: str,
    args: Any,
    mandate: list[ApprovedObligation],
    approvals: set[str],
) -> GuardDecision:
    """Allow, deny, or ask for approval. This function performs no I/O."""
    kind = classify(tool_name)
    if kind is ToolClass.READ:
        return GuardDecision("allow", "read-only tool", None)
    if kind is ToolClass.OTHER_WRITE:
        label = tool_name if isinstance(tool_name, str) else type(tool_name).__name__
        return GuardDecision("deny", f"tool {label} is not an allowed PayPal operation", None)
    if not isinstance(args, dict):
        return GuardDecision("deny", "tool arguments must be an object", None)
    if kind is ToolClass.MONEY_OUT:
        action_id = payment_action_id(tool_name.strip().lower(), args)
        if action_id in approvals:
            return GuardDecision("allow", f"approved payment action {action_id}", None)
        return GuardDecision("needs_approval", f"money-out requires approval {action_id}", None)
    return _decide_billing(tool_name.strip().lower(), args, mandate)


def payment_action_id(tool_name: str, args: dict[str, Any]) -> str:
    """Id bound to this exact tool name and canonical argument object."""
    from .receipts import canonical_json

    payload = canonical_json({"args": args, "tool": tool_name})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decide_billing(tool_name: str, args: dict[str, Any], mandate: list[ApprovedObligation]) -> GuardDecision:
    extra = _extra_recipient_reason(args)
    if extra is not None:
        return GuardDecision("deny", extra, None)
    emails, email_reason = _recipient_emails(args)
    if email_reason is not None:
        return GuardDecision("deny", email_reason, None)
    currency, currency_reason = _currency(args)
    if currency_reason is not None:
        return GuardDecision("deny", currency_reason, None)
    try:
        total = _total(args)
    except ValueError as exc:
        return GuardDecision("deny", str(exc), None)
    if total < 0:
        return GuardDecision("deny", "negative amount", None)

    payer = emails[0].lower()
    is_create = tool_name.startswith("create_")
    reasons: list[str] = []
    for obligation in mandate:
        reason = _obligation_mismatch(obligation, payer, currency, total, is_create)
        if reason is None:
            return GuardDecision("allow", f"matches approved obligation {obligation.id}", obligation.id)
        reasons.append(reason)
    if not mandate:
        return GuardDecision("deny", "no approved obligation matches the billing request", None)
    return GuardDecision("deny", "; ".join(reasons), None)


def _obligation_mismatch(
    obligation: ApprovedObligation,
    payer: str,
    currency: str,
    total: Decimal,
    is_create: bool,
) -> str | None:
    try:
        obligation_amount = _obligation_amount(obligation.amount)
    except ValueError:
        return f"obligation {obligation.id} has an invalid amount"
    obligation_email = obligation.payer_email.strip().lower()
    obligation_currency = obligation.currency.strip().upper()
    status = obligation.status.strip().upper()
    if payer != obligation_email:
        return f"recipient {payer} does not match obligation {obligation.id} payer {obligation_email}"
    if currency != obligation_currency:
        return f"currency {currency} does not match obligation {obligation.id} currency {obligation_currency}"
    if total > obligation_amount:
        return f"total {_money(total)} exceeds obligation {obligation.id} amount {_money(obligation_amount)}"
    if is_create and status in {"PAID", "INVOICED"}:
        return f"obligation {obligation.id} is already {status}"
    if status != "APPROVED":
        return f"obligation {obligation.id} status is {status}, not APPROVED"
    return None


def _extra_recipient_reason(args: dict[str, Any]) -> str | None:
    for key in _EXTRA_RECIPIENT_KEYS:
        if key in args and args[key]:
            return "extra recipients are not allowed"
    return None


def _recipient_emails(args: dict[str, Any]) -> tuple[list[str], str | None]:
    found: list[str] = []
    for key in _RECIPIENT_KEYS:
        if key not in args:
            continue
        found.extend(_emails_in(args[key]))
    unique: list[str] = []
    for email in found:
        if email.lower() not in {item.lower() for item in unique}:
            unique.append(email)
    if len(unique) > 1:
        return unique, "extra recipients are not allowed"
    if not unique:
        return [], "missing recipient email"
    return unique, None


def _emails_in(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return [text]
        return []
    if isinstance(value, dict):
        for key in ("email", "email_address", "recipient_email"):
            if key in value:
                return _emails_in(value[key])
        return []
    if isinstance(value, (list, tuple)):
        emails: list[str] = []
        for item in value:
            emails.extend(_emails_in(item))
        return emails
    return []


def _currency(args: dict[str, Any]) -> tuple[str | None, str | None]:
    found: list[str] = []
    for key in ("currency", "currency_code"):
        if args.get(key):
            found.append(str(args[key]).strip().upper())
    amount = args.get("amount")
    if isinstance(amount, dict) and amount.get("currency_code"):
        found.append(str(amount["currency_code"]).strip().upper())
    detail = args.get("detail")
    if isinstance(detail, dict) and detail.get("currency_code"):
        found.append(str(detail["currency_code"]).strip().upper())
    items = args.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("currency", "currency_code"):
                if item.get(key):
                    found.append(str(item[key]).strip().upper())
            unit_amount = item.get("unit_amount")
            if isinstance(unit_amount, dict) and unit_amount.get("currency_code"):
                found.append(str(unit_amount["currency_code"]).strip().upper())
    distinct = {code for code in found if code}
    if len(distinct) > 1:
        return None, "mixed currencies in tool arguments"
    if not distinct:
        return None, "missing currency"
    return distinct.pop(), None


def _total(args: dict[str, Any]) -> Decimal:
    explicit: Decimal | None = None
    for key in ("total", "amount", "invoice_total"):
        if key in args and args[key] is not None:
            explicit = _parse_amount(args[key])
            break
    item_total = _items_total(args.get("items"))
    if explicit is not None and item_total is not None and explicit != item_total:
        raise ValueError("total does not match line items")
    if explicit is not None:
        return explicit
    if item_total is not None:
        return item_total
    raise ValueError("missing amount")


def _items_total(items: Any) -> Decimal | None:
    if items is None:
        return None
    if not isinstance(items, list):
        raise ValueError("unparseable amount")
    if not items:
        return None
    total = Decimal(0)
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("unparseable amount")
        quantity = _parse_amount(item.get("quantity", 1))
        price = item.get("unit_price")
        if price is None:
            price = item.get("unit_amount")
        if price is None:
            raise ValueError("missing amount")
        total += quantity * _parse_amount(price)
    return total


def _parse_amount(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("unparseable amount")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("unparseable amount")
        amount = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if _AMOUNT_RE.fullmatch(text) is None:
            raise ValueError("unparseable amount")
        amount = Decimal(text)
    elif isinstance(value, dict):
        inner = None
        for key in ("value", "total", "amount"):
            if key in value:
                inner = value[key]
                break
        if inner is None:
            raise ValueError("unparseable amount")
        amount = _parse_amount(inner)
    else:
        raise ValueError("unparseable amount")
    if not amount.is_finite():
        raise ValueError("unparseable amount")
    return amount


def _obligation_amount(value: Decimal | str | int) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("invalid obligation amount")
    try:
        if isinstance(value, Decimal):
            amount = value
        else:
            amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid obligation amount") from exc
    if not amount.is_finite():
        raise ValueError("invalid obligation amount")
    return amount


def _money(amount: Decimal) -> str:
    return format(amount, "f")
