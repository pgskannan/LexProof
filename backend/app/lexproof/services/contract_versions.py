"""Durable contract-version creation boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from ..repositories.firestore import FirestoreRepository


class ContractVersionError(ValueError):
    """Base error for contract-version creation failures."""


class ContractNotFoundError(ContractVersionError):
    """Raised when the parent contract does not exist."""


class SourceVersionNotFoundError(ContractVersionError):
    """Raised when the source version does not exist or is unrelated."""


def create_contract_version(
    contract_id: str,
    source_version_id: str,
    version_data: Mapping[str, Any] | None,
    created_by: str,
    *,
    contracts: FirestoreRepository | None = None,
    versions: FirestoreRepository | None = None,
) -> dict[str, Any]:
    """Create and persist a child version without changing its source version."""
    contracts = contracts or FirestoreRepository("contracts")
    versions = versions or FirestoreRepository("contract_versions")

    contract = contracts.get(contract_id)
    if not contract:
        raise ContractNotFoundError(f"Contract not found: {contract_id}")

    source = versions.get(source_version_id)
    if not source or source.get("contract_id") != contract_id:
        raise SourceVersionNotFoundError(f"Source version not found: {source_version_id}")

    contract_versions = [
        record.get("version_number", 0)
        for record in versions.stream()
        if record.get("contract_id") == contract_id
    ]
    next_version_number = max(contract_versions or [source.get("version_number", 0)]) + 1
    now = datetime.now(timezone.utc).isoformat()
    new_version_id = str(uuid4())

    inherited_fields = {
        field: source[field]
        for field in ("storage_path", "content_hash", "filename", "content_type", "document_text")
        if field in source
    }
    inherited_fields.update(dict(version_data or {}))
    for field in ("id", "contract_id", "version_number", "parent_version_id", "created_at", "created_by", "passport_id"):
        inherited_fields.pop(field, None)
    inherited_fields["analysis_status"] = "pending"

    new_version = {
        **inherited_fields,
        "id": new_version_id,
        "owner_id": contract.get("owner_id") or source.get("owner_id") or created_by,
        "contract_id": contract_id,
        "version_number": next_version_number,
        "parent_version_id": source_version_id,
        "created_by": created_by,
        "created_at": now,
    }
    versions.set(new_version_id, new_version)
    contracts.set(contract_id, {"current_version_id": new_version_id, "updated_at": now}, merge=True)
    return new_version