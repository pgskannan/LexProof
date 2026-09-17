"""PII detection and masking utility.

Data-security hardening: contracts routinely contain personal data (SSNs,
emails, phone numbers, card numbers) inside quoted clause evidence. This
module detects common PII patterns and produces a masked version of text so
sensitive values are not shown by default in the UI -- findings, evidence
quotes, and anywhere else that surfaces raw contract text to a viewer who
may not need to see the unmasked value.

Deliberately regex-based and self-contained: no external PII-detection
service, no paid API, nothing to configure -- this is a complete, working
feature on its own, not a stub waiting on credentials.
"""

from __future__ import annotations

import re

# Ordered so more specific patterns (SSN, credit card) are tried before the
# looser phone-number pattern, since match order affects what mask_pii sees
# first when patterns could overlap on the same digits.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
}

PII_LABELS: dict[str, str] = {
    "ssn": "Social Security Number",
    "credit_card": "Credit card number",
    "email": "Email address",
    "phone": "Phone number",
}


def detect_pii(text: str | None) -> list[str]:
    """Return the sorted list of PII type keys found in `text` (empty if none/blank)."""
    if not text:
        return []
    found = {label for label, pattern in PII_PATTERNS.items() if pattern.search(text)}
    return sorted(found)


def mask_pii(text: str | None) -> str | None:
    """Return `text` with detected PII values replaced by a masked form.

    Non-destructive to structure: only the matched spans are replaced, so
    surrounding contract language stays intact and readable.
    """
    if not text:
        return text
    masked = text
    for label, pattern in PII_PATTERNS.items():
        masked = pattern.sub(lambda match, _label=label: _mask_match(_label, match.group(0)), masked)
    return masked


def _mask_match(label: str, value: str) -> str:
    if label == "email":
        local, _, domain = value.partition("@")
        if not local or not domain:
            return "***"
        return f"{local[0]}***@{domain}"
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 4:
        return "*" * len(digits)
    # Keep the last 4 digits visible (standard partial-redaction convention
    # for SSNs/cards/phone numbers), mask everything before them.
    return "*" * (len(digits) - 4) + digits[-4:]
