"""Canonical PayPal receipt hashing."""

from app.lexproof.services.paypal.guard import GuardDecision
from app.lexproof.services.paypal.receipts import canonical_json, canonical_receipt, receipt_hash, strip_sensitive


class _Model:
    def model_dump(self):
        return {"email": "payer@example.com", "access_token": "A21AAAAAAAAAAAAAAAAAAAAAAAA", "phone": "555-0100"}


def test_receipt_hash_is_canonical_and_strips_secrets():
    decision = GuardDecision("allow", "matches approved obligation ob-1", "ob-1")
    args = {
        "recipient_email": "payer@example.com",
        "currency": "USD",
        "total": "150.00",
        "access_token": "sandbox-token",
        "client_secret": "super-secret",
        "phone": "555-0100",
        "first_name": "Pat",
        "shipping_address": {"city": "Austin"},
    }
    response = {
        "id": "INV-1",
        "headers": {"Authorization": "Bearer abc.def"},
        "note": "Bearer abc.def was here",
        "payer": {"email_address": "payer@example.com", "name": "Pat"},
        "raw": "A21ABCDEFGHIJKLMNOPQRSTUV",
    }
    receipt = canonical_receipt("create_invoice", args, response, decision, "actor@example.com", "contract-1")
    assert receipt["decision"] == "allow"
    assert receipt["matched_obligation_id"] == "ob-1"
    assert receipt["args"]["recipient_email"] == "payer@example.com"
    assert "access_token" not in receipt["args"]
    assert "client_secret" not in receipt["args"]
    assert "phone" not in receipt["args"]
    assert "first_name" not in receipt["args"]
    assert "shipping_address" not in receipt["args"]
    assert "Authorization" not in receipt["response"]["headers"]
    assert receipt["response"]["payer"]["email_address"] == "payer@example.com"
    assert "name" not in receipt["response"]["payer"]
    assert "[redacted]" in receipt["response"]["note"]
    assert receipt["response"]["raw"] == "[redacted]"
    assert " " not in canonical_json({"b": 1, "a": 2})

    reordered = dict(reversed(list(receipt.items())))
    assert receipt_hash(receipt) == receipt_hash(reordered)
    changed = dict(receipt)
    changed["tool"] = "create_refund"
    assert receipt_hash(changed) != receipt_hash(receipt)


def test_receipt_accepts_dict_and_string_decisions_and_models():
    dumped = canonical_receipt(
        "list_invoices",
        {},
        _Model(),
        {"decision": "deny", "reason": "no", "matched_obligation_id": None},
        "Bearer abc.def",
        "contract-1",
    )
    assert dumped["decision"] == "deny"
    assert dumped["reason"] == "no"
    assert dumped["matched_obligation_id"] is None
    assert dumped["actor"] == "[redacted]"
    assert dumped["response"]["email"] == "payer@example.com"
    assert "access_token" not in dumped["response"]
    assert "phone" not in dumped["response"]

    plain = canonical_receipt("list_invoices", ["not-a-dict"], "ok", "allow", "actor", "c-1")
    assert plain["decision"] == "allow"
    assert plain["reason"] is None
    assert plain["args"] == ["not-a-dict"]
    assert plain["response"] == "ok"
    assert strip_sensitive(None) is None
    assert strip_sensitive(3) == 3
