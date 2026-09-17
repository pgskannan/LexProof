"""Authenticated retrieval of persisted AI contract findings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..repositories.firestore import FirestoreRepository
from ..services.pii import detect_pii, mask_pii
from ..services.auth import get_current_user
from ..services.organizations import get_organization_service
from ..services.translation import (
    SUPPORTED_LANGUAGES,
    TranslationError,
    TranslationService,
    get_translation_service,
)

router = APIRouter(prefix="/findings", tags=["findings"])


class FindingResponse(BaseModel):
    finding_id: str
    contract_id: Optional[str] = None
    version_id: Optional[str] = None
    title: str = ""
    severity: Optional[str] = None
    description: str = ""
    risk_impact: Optional[float] = None
    compliance_impact: Optional[float] = None
    evidence: Any = None
    evidence_quote: Optional[str] = None
    source_section: Optional[str] = None
    recommendation: Optional[str] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    clause_type: Optional[str] = None
    playbook_alignment: Optional[str] = None
    playbook_notes: Optional[str] = None
    regulatory_citations: list[str] = []
    evidence_quote_masked: Optional[str] = None
    contains_pii: bool = False
    detected_language: Optional[str] = None
    detected_language_name: Optional[str] = None
    evidence_validation: Optional[str] = None
    evidence_match_count: Optional[int] = None
    created_at: Optional[datetime] = None


def _visible(
    record: dict[str, Any],
    uid: str,
    contracts: FirestoreRepository | None = None,
) -> bool:
    contract_id = record.get("contract_id")
    if contract_id:
        contract = contracts.get(contract_id) if contracts else FirestoreRepository("contracts").get(contract_id)
        org_id = (contract or {}).get("org_id") or record.get("org_id")
        if org_id:
            return bool(get_organization_service().get_active_member(str(org_id), uid))
    owner_id = record.get("owner_id")
    return not owner_id or owner_id == uid


def _response(record: dict[str, Any]) -> FindingResponse:
    return FindingResponse(
        finding_id=str(record.get("finding_id") or record.get("id") or ""),
        contract_id=record.get("contract_id"),
        version_id=record.get("version_id"),
        title=str(record.get("title") or ""),
        severity=record.get("severity"),
        description=str(record.get("description") or ""),
        risk_impact=record.get("risk_impact"),
        compliance_impact=record.get("compliance_impact"),
        evidence=record.get("evidence"),
        evidence_quote=record.get("evidence_quote"),
        source_section=record.get("source_section"),
        recommendation=record.get("recommendation"),
        reasoning=record.get("reasoning"),
        confidence=record.get("confidence"),
        clause_type=record.get("clause_type"),
        playbook_alignment=record.get("playbook_alignment"),
        playbook_notes=record.get("playbook_notes"),
        regulatory_citations=list(record.get("regulatory_citations") or []),
        evidence_quote_masked=mask_pii(record.get("evidence_quote")) if record.get("evidence_quote") else None,
        contains_pii=bool(detect_pii(record.get("evidence_quote"))),
        detected_language=record.get("detected_language"),
        detected_language_name=record.get("detected_language_name"),
        evidence_validation=record.get("evidence_validation"),
        evidence_match_count=record.get("evidence_match_count"),
        created_at=record.get("created_at"),
    )


@router.get("", response_model=list[FindingResponse])
def list_findings(
    contract_id: Optional[str] = Query(None),
    version_id: Optional[str] = Query(None),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[FindingResponse]:
    """Return persisted findings visible to the authenticated user."""
    uid = str(user["uid"])
    repository = FirestoreRepository("risk_findings")
    contracts = FirestoreRepository("contracts")
    records = (
        record for record in repository.stream()
        if _visible(record, uid, contracts)
        and (contract_id is None or record.get("contract_id") == contract_id)
        and (version_id is None or record.get("version_id") == version_id)
    )
    return [_response(record) for record in records]


class TranslateFindingsRequest(BaseModel):
    finding_ids: list[str] = Field(min_length=1, max_length=50)
    target_language: str


class FindingTranslation(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    recommendation: Optional[str] = None
    playbook_notes: Optional[str] = None
    target_language: str


@router.get("/languages")
def list_supported_languages() -> dict[str, dict[str, str]]:
    """Target languages the translate endpoint accepts, code -> display name."""
    return {"languages": SUPPORTED_LANGUAGES}


@router.post("/translate", response_model=dict[str, FindingTranslation])
async def translate_findings(
    request: TranslateFindingsRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, FindingTranslation]:
    """Machine-translate a batch of findings' title/description/recommendation/
    playbook_notes into `target_language`, for a reviewer reading a non-English
    contract's findings in their own language. Results are cached per
    (finding, language) so repeated requests -- e.g. paging back and forth --
    don't re-call the translation provider. A finding_id the caller cannot
    see (belongs to another user) or that does not exist is silently omitted
    from the response rather than erroring the whole batch."""
    uid = str(user["uid"])
    try:
        translations = await get_translation_service().translate_findings(request.finding_ids, request.target_language, uid)
    except TranslationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {finding_id: FindingTranslation(**payload) for finding_id, payload in translations.items()}