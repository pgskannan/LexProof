"""Helpers for concise, speakable contract names and count grammar."""

from __future__ import annotations

import re
from typing import Any

_EXTENSIONS = (".docx", ".doc", ".pdf", ".txt")
_ACRONYMS = {
    "msa": "MSA",
    "nda": "NDA",
    "saas": "SaaS",
    "po": "PO",
    "psa": "PSA",
    "sow": "SOW",
}


def is_contract_filename(value: str | None) -> bool:
    name = str(value or "").strip().casefold()
    return any(name.endswith(extension) for extension in _EXTENSIONS)


def spoken_contract_name(name: str | None) -> str:
    """Normalize an uploaded file name for speech while preserving acronyms."""
    value = str(name or "").strip()
    if not value:
        return "contract"
    for extension in _EXTENSIONS:
        if value.casefold().endswith(extension):
            value = value[:-len(extension)]
            break
    chunks = re.split(r"[\s_-]+", value)
    words: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        acronym = _ACRONYMS.get(chunk.casefold())
        if acronym:
            words.append(acronym)
            continue
        parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[A-Z]+|\d+", chunk)
        words.extend(part.title() if part.isupper() else part for part in (parts or [chunk]))
    if len(words) >= 2 and words[0].isalpha() and words[1].isdigit():
        words = words[2:]
    return " ".join(words) or "contract"


def spoken_contract_mention(text: str, names: list[str]) -> str:
    """Replace known raw contract names inside a speech sentence."""
    result = text
    for name in sorted({name for name in names if name}, key=len, reverse=True):
        result = re.sub(re.escape(name), spoken_contract_name(name), result, flags=re.IGNORECASE)
    return result


def count_word(count: int) -> str:
    words = {0: "No", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
    return words.get(count, f"{count:,}")


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def amount_in_words(amount: Any, currency: str = "USD") -> str:
    from decimal import Decimal, InvalidOperation

    try:
        parsed = Decimal(str(amount or "0").replace(",", ""))
        rendered = f"{parsed:,.2f}" if parsed % 1 else f"{parsed:,.0f}"
    except (InvalidOperation, ValueError):
        rendered = str(amount or "0")
    currency_code = str(currency or "USD").upper()
    if currency_code == "USD":
        unit = pluralize(1 if rendered == "1" else 2, "dollar")
        return f"{rendered} {unit}"
    return f"{rendered} {currency_code}"


def spoken_payment_contract(obligation: dict[str, Any], contract_name: str) -> str:
    counterparty = str(obligation.get("counterparty") or "").strip()
    if counterparty and not is_contract_filename(counterparty):
        return spoken_contract_name(counterparty)
    return spoken_contract_name(contract_name)


def count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count:,} {pluralize(count, singular, plural)}"


def anchored_passport_phrase(count: int) -> str:
    if count == 1:
        return "1 has an anchored proof passport"
    return f"{count:,} have anchored proof passports"
