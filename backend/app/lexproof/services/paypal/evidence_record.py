"""Write a payment evidence record without an on-chain transaction.

The existing passport root anchor batches evidence hashes. These records are
stored in ``evidence_records`` so that batch can include them later. Nothing
here submits a per-event chain transaction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from ...domains.passport.utils.hashing import generate_evidence_id, hash_evidence_item
from ...repositories.firestore import FirestoreRepository

Repository = Any


def write_payment_evidence(
    *,
    evidence: Repository | None = None,
    passports: Repository | None = None,
    org_id: str,
    contract_id: str,
    actor_id: str,
    title: str,
    content: dict[str, Any],
    source_id: str,
    now: Callable[[], str] | None = None,
    transaction: Any = None,
    passport_id: str | None = None,
) -> str:
    """Persist one hashed evidence item and return its id."""
    evidence_repo = evidence if evidence is not None else FirestoreRepository("evidence_records")
    passport_repo = passports if passports is not None else FirestoreRepository("legal_passports")
    stamp = now() if now else datetime.now(timezone.utc).isoformat()
    evidence_id = generate_evidence_id()
    passport_id = passport_id or _passport_id(passport_repo, contract_id)
    item = {
        "evidence_id": evidence_id,
        "id": evidence_id,
        "passport_id": passport_id,
        "evidence_type": "audit_log",
        "title": title,
        "description": title,
        "content": json.dumps(content, sort_keys=True, separators=(",", ":"), default=str),
        "content_type": "application/json",
        "risk_impact": None,
        "compliance_impact": None,
        "evidence_status": "valid",
        "contract_reference": contract_id,
        "policy_reference": None,
        "analysis_reference": None,
        "source": "paypal_payment",
        "source_id": source_id,
        "metadata": {"org_id": org_id, "actor_id": actor_id},
        "owner_id": actor_id,
        "org_id": org_id,
        "contract_id": contract_id,
        "created_at": stamp,
        "hash": None,
    }
    item["hash"] = hash_evidence_item(item)
    evidence_repo.set(evidence_id, item, transaction=transaction)
    return evidence_id


def _passport_id(passports: Repository, contract_id: str) -> str:
    matches = [item for item in passports.stream() if item.get("contract_id") == contract_id]
    if not matches:
        return f"payment-{contract_id}"
    matches.sort(key=lambda item: str(item.get("created_at") or ""))
    chosen = matches[-1]
    return str(chosen.get("passport_id") or chosen.get("id") or f"payment-{contract_id}")
