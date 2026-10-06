"""Pure PaymentGuard for PayPal MCP tools.

Unknown tools are writes and are denied. Creating an invoice or order is
allowed only when the arguments match one approved obligation. Sending an
invoice is allowed only when that invoice is already in the LexProof ledger.
Money leaving the merchant requires an approval id bound to the exact tool
name and canonical arguments.
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
    label: str = ""


@dataclass(frozen=True)
class LedgerEntry:
    """One PayPal invoice LexProof created, keyed by invoice id."""

    obligation_id: str
    status: str
    obligation_status: str


@dataclass(frozen=True)
class GuardDecision:
    decision: str
    reason: str
    matched_obligation_id: str | None = None


_LEDGER_TOOLS = frozenset({"send_invoice", "send_invoice_reminder"})
_LEDGER_ARGUMENT = "invoice_id"
# inputSchema property names from docs/paypal-mcp-schemas.md (sandbox SSE, 2026-10-06).
_SEND_INVOICE_KEYS = frozenset({"invoice_id", "note", "send_to_recipient", "additional_recipients"})
_REMINDER_KEYS = frozenset({"invoice_id", "subject", "note", "additional_recipients"})


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
    invoice_ledger: dict[str, LedgerEntry] | None = None,
) -> GuardDecision:
    """Allow, deny, or ask for approval. This function performs no I/O.

    ``invoice_ledger`` maps a PayPal invoice id to the obligation LexProof
    created it for. Callers load it; this function does not.
    """
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
        return GuardDecision(
            "needs_approval",
            f"This payment needs a different person's approval before money leaves the merchant. Request {action_id}",
            None,
        )
    name = tool_name.strip().lower()
    if name in _LEDGER_TOOLS:
        return _decide_ledger(name, args, invoice_ledger or {})
    return _decide_billing(name, args, mandate)


def payment_action_id(tool_name: str, args: dict[str, Any]) -> str:
    """Id bound to this exact tool name and canonical argument object."""
    from .receipts import canonical_json

    payload = canonical_json({"args": args, "tool": tool_name})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# None means a scalar PayPal accepts. A dict describes an object, or each element of an array.
_CREATE_INVOICE_SCHEMA: dict[str, Any] = {
    "currency_code": None,
    "invoice_number": None,
    "invoice_date": None,
    "reference": None,
    "note": None,
    "invoicer_business_name": None,
    "invoicer_given_name": None,
    "invoicer_surname": None,
    "invoicer_email_address": None,
    "invoicer_tax_id": None,
    "invoicer_address_line_1": None,
    "invoicer_address_line_2": None,
    "invoicer_city": None,
    "invoicer_state": None,
    "invoicer_postal_code": None,
    "invoicer_country_code": None,
    "primary_recipients": {
        "billing_info": {
            "business_name": None,
            "name": {"given_name": None, "surname": None},
            "address": {
                "address_line_1": None,
                "address_line_2": None,
                "admin_area_2": None,
                "admin_area_1": None,
                "postal_code": None,
                "country_code": None,
            },
            "email_address": None,
            "phones": {"country_code": None, "national_number": None, "phone_type": None},
            "additional_info": None,
            "language": None,
        },
        "shipping_info": {
            "business_name": None,
            "name": {"given_name": None, "surname": None},
            "address": {
                "address_line_1": None,
                "address_line_2": None,
                "admin_area_2": None,
                "admin_area_1": None,
                "postal_code": None,
                "country_code": None,
            },
        },
    },
    "items": {
        "name": None,
        "description": None,
        "quantity": None,
        "unit_amount": {"currency_code": None, "value": None},
        "tax": {"name": None, "percent": None, "tax_note": None},
        "discount": {"percent": None, "amount": {"currency_code": None, "value": None}},
        "item_date": None,
        "unit_of_measure": None,
    },
    "allow_tip": None,
    "theme_color": None,
    "shipping_cost": None,
    "enable_pay_by_bank": None,
    "pay_by_bank_exclusive_above_threshold": None,
    "allow_partial_payment": None,
    "minimum_partial_payment_amount": None,
}
_CREATE_ORDER_SCHEMA: dict[str, Any] = {
    "currencyCode": None,
    "items": {
        "name": None,
        "quantity": None,
        "description": None,
        "itemCost": None,
        "taxPercent": None,
        "itemTotal": None,
    },
    "discount": None,
    "shippingCost": None,
    "shippingAddress": {
        "address_line_1": None,
        "address_line_2": None,
        "admin_area_2": None,
        "admin_area_1": None,
        "postal_code": None,
        "country_code": None,
    },
    "notes": None,
    "returnUrl": None,
    "cancelUrl": None,
}


def _decide_billing(tool_name: str, args: dict[str, Any], mandate: list[ApprovedObligation]) -> GuardDecision:
    if tool_name == "create_invoice":
        return _decide_create_invoice(args, mandate)
    if tool_name == "create_order":
        return _decide_create_order(args, mandate)
    return GuardDecision("deny", f"tool {tool_name} is not an allowed PayPal operation", None)


def _decide_create_invoice(args: dict[str, Any], mandate: list[ApprovedObligation]) -> GuardDecision:
    unexpected = _unexpected_in(args, _CREATE_INVOICE_SCHEMA)
    if unexpected:
        return GuardDecision("deny", f"unexpected argument {unexpected}", None)
    try:
        payer = _invoice_payer(args)
        currency, total = _invoice_total(args)
    except ValueError as exc:
        return GuardDecision("deny", str(exc), None)
    return _match_billing(mandate, payer, currency, total)


def _decide_create_order(args: dict[str, Any], mandate: list[ApprovedObligation]) -> GuardDecision:
    unexpected = _unexpected_in(args, _CREATE_ORDER_SCHEMA)
    if unexpected:
        return GuardDecision("deny", f"unexpected argument {unexpected}", None)
    try:
        currency, total = _order_total(args)
    except ValueError as exc:
        return GuardDecision("deny", str(exc), None)
    return _match_billing(mandate, None, currency, total)


def _unexpected_in(value: Any, schema: dict[str, Any]) -> str | None:
    """First key PayPal's schema does not declare. Arrays use the same object schema for every item."""
    if not isinstance(value, dict):
        return None
    extra = sorted(key for key in value if key not in schema)
    if extra:
        return extra[0]
    for key, child in value.items():
        spec = schema[key]
        if not isinstance(spec, dict):
            continue
        if isinstance(child, dict):
            found = _unexpected_in(child, spec)
        elif isinstance(child, list):
            found = None
            for item in child:
                found = _unexpected_in(item, spec)
                if found:
                    break
        else:
            found = None
        if found:
            return found
    return None


def _invoice_payer(args: dict[str, Any]) -> str:
    recipients = args.get("primary_recipients")
    if not isinstance(recipients, list) or not recipients:
        raise ValueError("missing recipient email")
    if len(recipients) != 1:
        raise ValueError("extra recipients are not allowed")
    recipient = recipients[0]
    if not isinstance(recipient, dict):
        raise ValueError("missing recipient email")
    billing = recipient.get("billing_info")
    if not isinstance(billing, dict):
        raise ValueError("missing recipient email")
    email = billing.get("email_address")
    if not isinstance(email, str) or not email.strip():
        raise ValueError("missing recipient email")
    return email.strip()


def _invoice_total(args: dict[str, Any]) -> tuple[str, Decimal]:
    raw_currency = args.get("currency_code")
    if not isinstance(raw_currency, str) or not raw_currency.strip():
        raise ValueError("missing currency")
    currency = raw_currency.strip().upper()
    items = args.get("items")
    if not isinstance(items, list):
        raise ValueError("unparseable amount")
    if not items:
        raise ValueError("missing amount")
    total = Decimal(0)
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("unparseable amount")
        unit = item.get("unit_amount")
        if not isinstance(unit, dict):
            raise ValueError("missing amount")
        unit_currency = unit.get("currency_code")
        if not isinstance(unit_currency, str) or not unit_currency.strip():
            raise ValueError("missing currency")
        if unit_currency.strip().upper() != currency:
            raise ValueError("mixed currencies in tool arguments")
        if "quantity" not in item:
            raise ValueError("missing amount")
        quantity = _parse_amount(item.get("quantity"))
        price = _parse_amount(unit.get("value"))
        if quantity < 0 or price < 0:
            raise ValueError("negative amount")
        _reject_adjustment(item.get("tax"), "tax")
        _reject_adjustment(item.get("discount"), "discount")
        total += quantity * price
    _reject_adjustment(args.get("shipping_cost"), "shipping")
    return currency, total


def _order_total(args: dict[str, Any]) -> tuple[str, Decimal]:
    raw_currency = args.get("currencyCode")
    if not isinstance(raw_currency, str) or not raw_currency.strip():
        raise ValueError("missing currency")
    currency = raw_currency.strip().upper()
    items = args.get("items")
    if not isinstance(items, list):
        raise ValueError("unparseable amount")
    if not items:
        raise ValueError("missing amount")
    _reject_adjustment(args.get("discount"), "discount")
    _reject_adjustment(args.get("shippingCost"), "shipping")
    total = Decimal(0)
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("unparseable amount")
        if "itemCost" not in item or "itemTotal" not in item:
            raise ValueError("missing amount")
        quantity = _parse_amount(item.get("quantity", 1))
        cost = _parse_amount(item.get("itemCost"))
        line = _parse_amount(item.get("itemTotal"))
        if quantity < 0 or cost < 0 or line < 0:
            raise ValueError("negative amount")
        if quantity * cost != line:
            raise ValueError("total does not match line items")
        _reject_adjustment(item.get("taxPercent"), "tax")
        total += line
    return currency, total


def _reject_adjustment(value: Any, kind: str) -> None:
    """Tax, discount, and shipping change the amount PayPal collects. Zero is fine; anything else is not."""
    if value is None or value == "" or value == {} or value is False:
        return
    if isinstance(value, dict):
        if "percent" in value:
            _reject_adjustment(value.get("percent"), kind)
        if "amount" in value:
            _reject_adjustment(value.get("amount"), kind)
        if "value" in value:
            _reject_adjustment(value.get("value"), kind)
        return
    amount = _parse_amount(value)
    if amount != 0:
        raise ValueError(f"non-zero {kind} is not allowed")


def _match_billing(
    mandate: list[ApprovedObligation],
    payer: str | None,
    currency: str,
    total: Decimal,
) -> GuardDecision:
    status_reason: str | None = None
    invalid_reason: str | None = None
    for obligation in mandate:
        if not _money_fits(obligation, payer, currency, total):
            if invalid_reason is None:
                try:
                    _obligation_amount(obligation.amount)
                except ValueError:
                    invalid_reason = f"obligation {obligation.id} has an invalid amount"
            continue
        reason = _status_reason(obligation)
        if reason is None:
            return GuardDecision("allow", f"matches approved obligation {obligation.id}", obligation.id)
        if status_reason is None:
            status_reason = reason
    if status_reason:
        return GuardDecision("deny", status_reason, None)
    if invalid_reason and all(_amount_invalid(item) for item in mandate):
        return GuardDecision("deny", invalid_reason, None)
    return GuardDecision("deny", _closest_reason(currency, total, mandate), None)


def _amount_invalid(obligation: ApprovedObligation) -> bool:
    try:
        _obligation_amount(obligation.amount)
    except ValueError:
        return True
    return False


def _money_fits(obligation: ApprovedObligation, payer: str | None, currency: str, total: Decimal) -> bool:
    try:
        obligation_amount = _obligation_amount(obligation.amount)
    except ValueError:
        return False
    if payer is not None and payer.lower() != obligation.payer_email.strip().lower():
        return False
    if currency != obligation.currency.strip().upper():
        return False
    return total <= obligation_amount


def _status_reason(obligation: ApprovedObligation) -> str | None:
    status = obligation.status.strip().upper()
    if status in {"PAID", "INVOICED"}:
        return f"obligation {obligation.id} is already {status}"
    if status != "APPROVED":
        return f"obligation {obligation.id} status is {status}, not APPROVED"
    return None


def _closest_reason(currency: str, total: Decimal, mandate: list[ApprovedObligation]) -> str:
    scored: list[tuple[Decimal, str, str, Decimal]] = []
    for obligation in mandate:
        try:
            amount = _obligation_amount(obligation.amount)
        except ValueError:
            continue
        label = obligation.label.strip() or obligation.id
        scored.append((abs(amount - total), label, obligation.currency.strip().upper() or currency, amount))
    scored.sort(key=lambda item: (item[0], item[1]))
    closest = ", ".join(f"{label} {code} {_money(amount)}" for _, label, code, amount in scored[:2])
    text = f"No approved obligation allows {currency} {_money(total)}"
    if closest:
        text += f" (closest: {closest})"
    return text


def _decide_ledger(tool_name: str, args: dict[str, Any], ledger: dict[str, LedgerEntry]) -> GuardDecision:
    """Send and reminder arguments must be keys PayPal's MCP schema accepts."""
    allowed = _SEND_INVOICE_KEYS if tool_name == "send_invoice" else _REMINDER_KEYS
    unexpected = _unexpected_in(args, {key: None for key in allowed})
    if unexpected:
        return GuardDecision("deny", f"unexpected argument {unexpected}", None)
    if args.get("additional_recipients"):
        return GuardDecision("deny", "extra recipients are not allowed", None)
    invoice_id = args.get(_LEDGER_ARGUMENT)
    if not isinstance(invoice_id, str) or not invoice_id.strip():
        return GuardDecision("deny", "missing invoice_id", None)
    invoice_id = invoice_id.strip()
    entry = ledger.get(invoice_id)
    if entry is None:
        return GuardDecision("deny", f"unknown invoice_id {invoice_id} was not created by LexProof", None)
    obligation_status = entry.obligation_status.strip().upper()
    ledger_status = entry.status.strip().upper()
    if obligation_status == "CANCELLED" or ledger_status == "CANCELLED":
        return GuardDecision("deny", f"obligation {entry.obligation_id} is cancelled", entry.obligation_id)
    if tool_name == "send_invoice":
        if obligation_status not in {"APPROVED", "INVOICED"}:
            return GuardDecision(
                "deny",
                f"obligation {entry.obligation_id} status is {obligation_status}, not APPROVED or INVOICED",
                entry.obligation_id,
            )
        if ledger_status != "DRAFT":
            return GuardDecision(
                "deny",
                f"invoice {invoice_id} status is {ledger_status}, not DRAFT",
                entry.obligation_id,
            )
        return GuardDecision("allow", f"send matches ledger invoice {invoice_id}", entry.obligation_id)
    if ledger_status != "SENT":
        return GuardDecision(
            "deny",
            f"invoice {invoice_id} status is {ledger_status}, not SENT",
            entry.obligation_id,
        )
    if obligation_status == "PAID":
        return GuardDecision("deny", f"obligation {entry.obligation_id} is PAID", entry.obligation_id)
    return GuardDecision("allow", f"reminder matches sent invoice {invoice_id}", entry.obligation_id)


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
    return f"{amount.quantize(Decimal('0.01')):,.2f}"
