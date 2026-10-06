"""Persist and anchor one append-only PayPal receipt-chain checkpoint."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from ...config import LexProofSettings, get_settings
from ...repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository
from ..ethereum_anchor_service import get_ethereum_anchor_service
from .checkpoint import chain_head, order_receipts
from .evidence_record import write_payment_evidence
from .obligations import PaymentError
from .public_chain import public_receipt_canonical
from .receipts import receipt_hash


async def create_payment_checkpoint(
    *,
    contract_id: str,
    org_id: str,
    actor_id: str,
    receipts: Any,
    checkpoints: Any,
    evidence: Any,
    passports: Any,
    settings: LexProofSettings | None = None,
    anchor_service_factory: Callable[..., Any] | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Create one checkpoint, submit its evidence hash, and persist the proof."""
    receipt_rows = [
        {**item, "id": str(item.get("id") or "")}
        for item in receipts.stream()
        if item.get("contract_id") == contract_id and item.get("org_id") == org_id
    ]
    receipt_rows = order_receipts(receipt_rows)
    prior = [
        item for item in checkpoints.stream()
        if item.get("contract_id") == contract_id and item.get("org_id") == org_id
    ]
    latest = max(prior, key=lambda item: (int(item.get("count") or 0), str(item.get("created_at") or "")), default=None)
    previous_count = int((latest or {}).get("count") or 0)
    if len(receipt_rows) <= previous_count:
        raise PaymentError(409, "There are no new payment receipts to checkpoint")

    chain_receipts = [
        {**item, "receipt_hash": receipt_hash(public_receipt_canonical(item))}
        for item in receipt_rows
    ]
    head, count = chain_head(contract_id, chain_receipts)
    checkpoint_id = str(uuid4())
    stamp = now() if now else datetime.now(timezone.utc).isoformat()
    evidence_content = {
        "contract_id": contract_id,
        "count": count,
        "last_receipt_id": str(receipt_rows[-1].get("id") or ""),
        "chain_head": head,
    }
    evidence_id = write_payment_evidence(
        evidence=evidence,
        passports=passports,
        org_id=org_id,
        contract_id=contract_id,
        actor_id=actor_id,
        title=f"PayPal payment chain checkpoint #{count}",
        content=evidence_content,
        source_id=checkpoint_id,
        now=lambda: stamp,
    )

    settings = settings or get_settings()
    anchor_repository = EvidenceAnchorRepository("evidence_anchors", settings=settings)
    evidence_records_repository = EvidenceRecordRepository(anchor_repository, settings=settings)
    factory = anchor_service_factory or get_ethereum_anchor_service
    anchor_service = await asyncio.to_thread(
        factory,
        settings=settings,
        repository=anchor_repository,
        evidence_repository=evidence_records_repository,
    )
    proof = await anchor_service.anchor_evidence(evidence_id, actor_id=actor_id, org_id=org_id)
    transaction_hash = str(proof.get("transaction_hash") or "")
    if not transaction_hash:
        raise RuntimeError("Ethereum anchor service returned no confirmed transaction hash")

    checkpoint = {
        "id": checkpoint_id,
        "contract_id": contract_id,
        "org_id": org_id,
        "count": count,
        "first_receipt_id": str(receipt_rows[0].get("id") or ""),
        "last_receipt_id": str(receipt_rows[-1].get("id") or ""),
        "chain_head": head,
        "created_by": actor_id,
        "created_at": stamp,
        "evidence_id": evidence_id,
        "transaction_hash": transaction_hash,
        "block_number": proof.get("block_number"),
        "anchored_at": proof.get("anchored_at"),
    }
    checkpoints.set(checkpoint_id, checkpoint)
    return checkpoint


def payment_chain_snapshot(contract_id: str, org_id: str, receipts: Any) -> tuple[list[dict[str, Any]], str, int]:
    """Build the public-canonical receipt list and head for dry runs."""
    rows = order_receipts([
        {**item, "id": str(item.get("id") or "")}
        for item in receipts.stream()
        if item.get("contract_id") == contract_id and item.get("org_id") == org_id
    ])
    chain_receipts = [
        {**item, "receipt_hash": receipt_hash(public_receipt_canonical(item))}
        for item in rows
    ]
    head, count = chain_head(contract_id, chain_receipts)
    return rows, head, count
