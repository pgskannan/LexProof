"""Legal Passport API endpoints.

Provides REST API endpoints for creating, retrieving, and managing
contract passports and evidence items.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, Optional
from uuid import UUID

from ..service import PassportService
from ..evidence_service import EvidenceService
from ..models import (
    ContractPassportCreate,
    ContractPassportResponse,
    ContractPassportSummary,
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceItemUpdate,
    EvidenceItemSummary,
    PassportStatus,
)
from ....repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository, FirestoreRepository
from ....services.auth import get_current_user
from ..integrity import verify_passport_integrity

router = APIRouter(prefix="/passports", tags=["Legal Passports"])
contract_router = APIRouter(prefix="/contracts", tags=["Legal Passports"])


# ─────────────────────────────────────────────────────────────────────────────────
# Passport Endpoints
# ─────────────────────────────────────────────────────────────────────────────────

_passport_service: Optional[PassportService] = None
_evidence_anchor_repository = EvidenceAnchorRepository("evidence_anchors")
_evidence_service = EvidenceService(
    EvidenceRecordRepository(_evidence_anchor_repository),
    passport_repository=FirestoreRepository("legal_passports"),
    anchor_repository=_evidence_anchor_repository,
)


async def _analysis_engine(document: str, policy: str) -> Dict[str, Any]:
    """Adapter boundary for ContractRiskEdge's existing analysis engine.

    Deployments should replace this dependency with the existing AIService
    method; this module never performs a second AI analysis implementation.
    """
    raise RuntimeError("ContractRiskEdge analysis engine adapter is not configured")


def get_passport_service() -> PassportService:
    if _passport_service is None:
        return PassportService(
            analysis_engine=_analysis_engine,
            user_id="read-only",
            tenant_id="read-only",
            repository=FirestoreRepository("legal_passports"),
        )
    return _passport_service


def configure_passport_service(service: PassportService) -> None:
    """Bind the existing ContractRiskEdge analysis service at application startup."""
    global _passport_service
    _passport_service = service


def get_read_passport_service(user: Dict[str, Any]) -> PassportService:
    return PassportService(
        analysis_engine=_analysis_engine,
        user_id=str(user["uid"]),
        tenant_id=str(user["uid"]),
        repository=FirestoreRepository("legal_passports"),
    )


@router.post("", response_model=ContractPassportResponse)
async def create_passport(
    body: ContractPassportCreate,
    service: PassportService = Depends(get_passport_service),
):
    """Create a new legal passport for a contract.

    This endpoint triggers AI analysis using the existing ContractRiskEdge
    engine and creates an immutable passport snapshot with all intelligence
    data and cryptographic fingerprints.
    """
    service = get_passport_service()
    return await service.create_passport(
        contract_id=body.contract_id,
        contract_version=body.contract_version,
        policy_version=body.policy_version,
        document_content=body.document_content,
        normalized_document=body.normalized_document,
        policy_content=body.policy_content,
    )


@router.get("/{passport_id}", response_model=ContractPassportResponse)
async def get_passport(
    passport_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve a passport by ID."""
    passport = await get_read_passport_service(user).get_passport(passport_id)

    if not passport:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found: {passport_id}"
        )

    return passport


@contract_router.get("/{contract_id}/passport", response_model=ContractPassportResponse)
async def get_passport_by_contract(
    contract_id: str,
    contract_version: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve a passport by contract and version."""
    passport = await get_read_passport_service(user).get_passport_by_contract(
        contract_id=contract_id,
        contract_version=contract_version,
    )

    if not passport:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found for contract {contract_id}, version {contract_version}"
        )

    return passport


@router.get("", response_model=list[ContractPassportSummary])
async def list_passports(
    contract_id: Optional[str] = Query(None, description="Filter by contract ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of passports"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List passports with optional filtering."""
    passports = await get_passport_service().list_passports(
        contract_id=contract_id,
        limit=limit,
        offset=offset,
    )

    return passports


@router.get("/{passport_id}/status")
async def get_passport_status(
    passport_id: str,
):
    """Get passport status."""
    passport = await get_passport_service().get_passport(passport_id)

    if not passport:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found: {passport_id}"
        )

    return {
        "passport_id": passport.passport_id,
        "status": passport.status,
        "risk_score": passport.risk_score,
        "compliance_score": passport.compliance_score,
        "created_at": passport.created_at,
    }


# ─────────────────────────────────────────────────────────────────────────────────
# Evidence Endpoints
# ─────────────────────────────────────────────────────────────────────────────────

async def get_evidence_service(user: Dict[str, Any] = Depends(get_current_user)) -> EvidenceService:
    """Get EvidenceService instance."""
    return EvidenceService(
        _evidence_service.repository,
        owner_id=str(user["uid"]),
        passport_repository=_evidence_service.passport_repository,
        anchor_repository=_evidence_service.anchor_repository,
    )


@router.post("/evidence", response_model=EvidenceItemResponse)
async def create_evidence_item(
    body: EvidenceItemCreate,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Create a new evidence item for a passport."""
    evidence_item = await service.create_evidence_item(
        passport_id=body.passport_id,
        evidence_data=body,
        user=None,
    )

    return evidence_item


@router.get("/evidence/{evidence_id}", response_model=EvidenceItemResponse)
async def get_evidence_item(
    evidence_id: str,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Retrieve an evidence item by ID."""
    evidence_item = await service.get_evidence_item(evidence_id)

    if not evidence_item:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return evidence_item


@router.get("/{passport_id}/evidence", response_model=list[EvidenceItemSummary])
async def get_evidence_by_passport(
    passport_id: UUID,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Retrieve all evidence items for a passport."""
    passport_id_value = str(passport_id)
    if not service.passport_exists(passport_id_value):
        raise HTTPException(status_code=404, detail=f"Passport not found: {passport_id_value}")
    evidence_items = await service.get_evidence_by_passport(passport_id_value)

    return evidence_items


@router.put("/evidence/{evidence_id}", response_model=EvidenceItemResponse)
async def update_evidence_item(
    evidence_id: str,
    body: EvidenceItemUpdate,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Update an evidence item."""
    evidence_item = await service.update_evidence_item(
        evidence_id=evidence_id,
        update_data=body,
    )

    if not evidence_item:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return evidence_item


@router.delete("/evidence/{evidence_id}")
async def delete_evidence_item(
    evidence_id: str,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Delete an evidence item."""
    success = await service.delete_evidence_item(evidence_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return {"message": "Evidence item deleted successfully"}


@router.post("/evidence/{evidence_id}/verify", response_model=EvidenceItemResponse)
async def verify_evidence_item(
    evidence_id: str,
    verification_data: Optional[Dict[str, Any]] = None,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Verify an evidence item."""
    evidence_item = await service.verify_evidence_item(
        evidence_id=evidence_id,
        verification_data=verification_data,
    )

    if not evidence_item:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return evidence_item


@router.get("/{passport_id}/evidence/statistics")
async def get_evidence_statistics(
    passport_id: UUID,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Get statistics for evidence items in a passport."""
    passport_id_value = str(passport_id)
    if not service.passport_exists(passport_id_value):
        raise HTTPException(status_code=404, detail=f"Passport not found: {passport_id_value}")
    statistics = await service.get_evidence_statistics(passport_id_value)

    return statistics


@router.post("/{passport_id}/verify")
async def verify_passport_integrity_endpoint(
    passport_id: UUID,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Verify passport integrity by recomputing hashes.

    This endpoint never trusts the frontend hash. It recomputes all
    cryptographic hashes from the persisted data and compares them
    with the stored hash in metadata.passport_hash.

    Args:
        passport_id: Passport ID to verify

    Returns:
        Verification result with verified status and component details
    """
    passport_id_value = str(passport_id)
    passport_service = get_read_passport_service(user)

    passport_doc: Dict[str, Any] | None = None
    passport_response = await passport_service.get_passport(passport_id_value)
    if passport_response:
        passport_doc = passport_response.model_dump(mode="json")
    else:
        repository = FirestoreRepository("legal_passports")
        stored = repository.get(passport_id_value)
        if stored and stored.get("owner_id") == str(user["uid"]):
            passport_doc = stored

    if not passport_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found: {passport_id_value}"
        )

    evidence_items = await passport_service.get_evidence(passport_id_value)
    if not evidence_items:
        evidence_service = await get_evidence_service(user)
        if evidence_service.repository is not None:
            evidence_items = [
                record
                for record in evidence_service.repository.stream()
                if record.get("passport_id") == passport_id_value
                and (not evidence_service.owner_id or record.get("owner_id") == evidence_service.owner_id)
            ]

    return verify_passport_integrity(passport_doc, evidence_items=evidence_items)
