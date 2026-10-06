"""Pure hash-chain operations for PayPal payment checkpoints."""

from __future__ import annotations

import hashlib
from typing import Any

CHAIN_VERSION = "lexproof-payments-v1"


def order_receipts(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order receipts deterministically by creation time, then document id."""
    return sorted(
        receipts,
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")),
    )


def chain_head(contract_id: str, receipts: list[dict[str, Any]]) -> tuple[str, int]:
    """Return the versioned chain head and receipt count."""
    head = hashlib.sha256(f"{CHAIN_VERSION}:{contract_id}".encode("utf-8")).hexdigest()
    ordered = order_receipts(receipts)
    for receipt in ordered:
        digest = str(receipt.get("receipt_hash") or "").lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"Receipt {receipt.get('id') or '<unknown>'} has an invalid receipt_hash")
        head = hashlib.sha256(f"{head}{digest}".encode("utf-8")).hexdigest()
    return head, len(ordered)


def coverage(
    receipts: list[dict[str, Any]], checkpoints: list[dict[str, Any]],
) -> dict[str, dict[str, Any] | None]:
    """Map each receipt id to its first anchored checkpoint, if covered."""
    ordered_receipts = order_receipts(receipts)
    anchored = sorted(
        (
            checkpoint for checkpoint in checkpoints
            if checkpoint.get("transaction_hash")
        ),
        key=lambda item: (int(item.get("count") or 0), str(item.get("created_at") or ""), str(item.get("id") or "")),
    )
    result: dict[str, dict[str, Any] | None] = {}
    for index, receipt in enumerate(ordered_receipts, start=1):
        receipt_id = str(receipt.get("id") or "")
        result[receipt_id] = next(
            (checkpoint for checkpoint in anchored if int(checkpoint.get("count") or 0) >= index),
            None,
        )
    return result