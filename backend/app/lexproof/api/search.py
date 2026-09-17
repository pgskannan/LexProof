"""Global search across the signed-in user's contracts, findings, and passports.

A single lightweight endpoint the frontend's search bar calls, rather than a
separate query per collection. Matching is a case-insensitive substring check
over each collection's user-facing text fields -- there is no full-text search
index configured for this Firestore project, and the demo dataset is small
enough that a per-request scan is fine. Results are scoped to the same
owner-visibility rule used everywhere else in the app (a record with no
owner_id is a legacy/seed record visible to everyone; otherwise it must match
the caller's uid).
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_user

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    type: str  # "contract" | "finding" | "passport"
    id: str
    title: str
    subtitle: str = ""
    contract_id: Optional[str] = None
    url: str


def _visible(record: dict[str, Any], uid: str) -> bool:
    owner_id = record.get("owner_id")
    return not owner_id or owner_id == uid


def _matches(query: str, *fields: Any) -> bool:
    for field in fields:
        if field and query in str(field).lower():
            return True
    return False


def _contract_name(record: dict[str, Any]) -> str:
    return (
        record.get("name")
        or record.get("contract_name")
        or (record.get("metadata") or {}).get("contract_name")
        or record.get("contract_id")
        or record.get("id")
        or "Untitled contract"
    )


@router.get("", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=1, description="Search text"),
    limit: int = Query(30, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[SearchResult]:
    """Search contracts, findings, and legal passports by their visible text."""
    uid = str(user["uid"])
    query = q.strip().lower()
    if not query:
        return []

    # The three collection scans below go through the real, synchronous
    # Firestore SDK client. Called directly inside this async endpoint (which
    # the command palette now calls on every keystroke), a full scan of each
    # collection would run on the event loop's own thread and block every
    # other concurrent request on it -- the same status-and-plan.md "§2c"
    # class of hang already fixed in evidence_service.py. Push the whole scan
    # onto a worker thread so it can't stall the loop.
    def _scan() -> list[SearchResult]:
        found: list[SearchResult] = []

        contracts = FirestoreRepository("contracts")
        for record in contracts.stream():
            if not _visible(record, uid):
                continue
            name = _contract_name(record)
            if not _matches(query, name, record.get("id"), record.get("contract_id")):
                continue
            contract_id = record.get("id") or record.get("contract_id")
            found.append(SearchResult(
                type="contract",
                id=str(contract_id),
                title=str(name),
                subtitle=f"Status: {record.get('status') or 'unknown'}",
                contract_id=str(contract_id) if contract_id else None,
                url=f"/dashboard/contracts/{contract_id}",
            ))

        findings = FirestoreRepository("risk_findings")
        for record in findings.stream():
            if not _visible(record, uid):
                continue
            if not _matches(query, record.get("title"), record.get("description"), record.get("evidence_quote")):
                continue
            finding_id = record.get("finding_id") or record.get("id")
            contract_id = record.get("contract_id")
            found.append(SearchResult(
                type="finding",
                id=str(finding_id),
                title=str(record.get("title") or "Untitled finding"),
                subtitle=str(record.get("severity") or "").upper(),
                contract_id=str(contract_id) if contract_id else None,
                url=f"/dashboard/contracts/{contract_id}" if contract_id else "/dashboard/findings",
            ))

        passports = FirestoreRepository("legal_passports")
        for record in passports.stream():
            if not _visible(record, uid):
                continue
            passport_id = record.get("passport_id") or record.get("id")
            contract_id = record.get("contract_id")
            name = _contract_name(record)
            if not _matches(query, name, passport_id, contract_id):
                continue
            found.append(SearchResult(
                type="passport",
                id=str(passport_id),
                title=str(name),
                subtitle=f"Passport {passport_id}",
                contract_id=str(contract_id) if contract_id else None,
                url=f"/legal-passport?contractId={contract_id}&contractVersion={record.get('contract_version') or 1}",
            ))

        return found

    results = await asyncio.to_thread(_scan)

    def _rank(result: SearchResult) -> tuple[int, str]:
        # Exact/prefix matches on the title surface above substring matches.
        title = result.title.lower()
        if title == query:
            return (0, title)
        if title.startswith(query):
            return (1, title)
        return (2, title)

    results.sort(key=_rank)
    return results[:limit]
