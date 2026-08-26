"""
Evidence Anchor API endpoints for LexProof.

Provides endpoints for anchoring evidence records to Ethereum and
verifying evidence against blockchain anchors.

SECURITY: Only hashes are stored on-chain. Never stores evidence content,
PII, or sensitive data.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..services.ethereum_anchor_service import (
    EthereumAnchorService,
    get_ethereum_anchor_service,
)
from ..repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository, FirestoreRepository
from ..config import LexProofSettings, get_settings

router = APIRouter(tags=["evidence-anchor"])


def get_evidence_repository(settings: LexProofSettings = Depends(get_settings)) -> FirestoreRepository:
    return EvidenceAnchorRepository("evidence_anchors", settings=settings)


def get_evidence_records_repository(settings: LexProofSettings = Depends(get_settings)) -> FirestoreRepository:
    return EvidenceRecordRepository(
        EvidenceAnchorRepository("evidence_anchors", settings=settings),
        settings=settings,
    )


# Pydantic models
class EvidenceAnchorRequest(BaseModel):
    """Request model for evidence anchoring."""
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(..., description="Evidence record identifier")


class EvidenceAnchorResponse(BaseModel):
    """Response model for evidence anchoring."""
    evidence_id: str
    blockchain_network: str
    contract_address: str
    transaction_hash: str
    block_number: int
    anchored_at: str
    evidence_hash: str


class EvidenceVerificationResult(BaseModel):
    """Response model for evidence verification."""
    verified: bool
    status: str
    evidence_hash_on_chain: Optional[str] = None
    computed_hash: Optional[str] = None
    blockchain_network: Optional[str] = None
    contract_address: Optional[str] = None
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    anchored_at: Optional[str] = None


@router.post(
    "/evidence/{evidence_id}/anchor",
    response_model=EvidenceAnchorResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Anchor evidence to Ethereum"
)
async def anchor_evidence_to_blockchain(
    evidence_id: str,
    request: EvidenceAnchorRequest,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository),
    evidence_records_repository: FirestoreRepository = Depends(get_evidence_records_repository)
) -> EvidenceAnchorResponse:
    """
    Anchor an evidence record to Ethereum.

    SECURITY: Only the evidence_hash is stored on-chain. Never stores evidence content,
    PII, or sensitive data.

    Args:
        evidence_id: Evidence record identifier
        request: Evidence anchoring request
        settings: LexProof settings (injected)
        repository: Firestore repository (injected)

    Returns:
        Evidence anchor response with transaction details

    Raises:
        HTTPException: If validation fails or transaction fails
    """
    try:
        if request.evidence_id != evidence_id:
            raise ValueError("Evidence ID in request must match path parameter")
        # Initialize services
        anchor_service = get_ethereum_anchor_service(
            settings=settings,
            repository=repository,
            evidence_repository=evidence_records_repository,
        )

        # Anchor evidence
        result = await anchor_service.anchor_evidence(
            evidence_id=request.evidence_id,
        )

        return EvidenceAnchorResponse(
            evidence_id=request.evidence_id,
            blockchain_network=result["blockchain_network"],
            contract_address=result["contract_address"],
            transaction_hash=result["transaction_hash"],
            block_number=result["block_number"],
            anchored_at=result["anchored_at"],
            evidence_hash=result["evidence_hash"],
        )

    except ValueError as e:
        if str(e).startswith("Evidence record not found"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error anchoring evidence to Ethereum: {str(e)}"
        )


@router.get(
    "/evidence/{evidence_id}/anchor",
    response_model=Dict[str, Any],
    summary="Get evidence anchor details"
)
async def get_evidence_anchor(
    evidence_id: str,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository)
) -> Dict[str, Any]:
    """
    Get Ethereum anchor details for an evidence record.

    Args:
        evidence_id: Evidence record identifier
        settings: LexProof settings (injected)
        repository: Firestore repository (injected)

    Returns:
        Evidence anchor details

    Raises:
        HTTPException: If anchor not found
    """
    try:
        # Initialize service
        anchor_service = get_ethereum_anchor_service(
            settings=settings,
            repository=repository
        )

        # Retrieve anchor from repository
        if not repository:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository required to retrieve anchor details"
            )

        result = repository.get(evidence_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evidence anchor not found for evidence_id: {evidence_id}"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving evidence anchor: {str(e)}"
        )


@router.post(
    "/evidence/{evidence_id}/verify",
    response_model=EvidenceVerificationResult,
    summary="Verify evidence on Ethereum"
)
async def verify_evidence_on_blockchain(
    evidence_id: str,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository),
    evidence_records_repository: FirestoreRepository = Depends(get_evidence_records_repository)
) -> EvidenceVerificationResult:
    """
    Verify an evidence record against its Ethereum anchor.

    SECURITY: This is a read-only operation. It does not expose any sensitive data.

    Args:
        evidence_id: Evidence record identifier
        settings: LexProof settings (injected)
        repository: Firestore repository (injected)

    Returns:
        Verification result

    Raises:
        HTTPException: If verification fails
    """
    try:
        # Initialize service
        anchor_service = get_ethereum_anchor_service(
            settings=settings,
            repository=repository,
            evidence_repository=evidence_records_repository,
        )

        # Verify evidence
        result = anchor_service.verify_evidence(
            evidence_id=evidence_id,
        )

        return EvidenceVerificationResult(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying evidence on Ethereum: {str(e)}"
        )


@router.get(
    "/evidence/{evidence_id}/status",
    response_model=Dict[str, Any],
    summary="Get evidence anchoring status"
)
async def get_evidence_anchor_status(
    evidence_id: str,
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository)
) -> Dict[str, Any]:
    """
    Get anchoring status for an evidence record.

    Args:
        evidence_id: Evidence record identifier
        settings: LexProof settings (injected)
        repository: Firestore repository (injected)

    Returns:
        Status information including whether evidence is anchored

    Raises:
        HTTPException: If status retrieval fails
    """
    try:
        if not repository:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Repository required to check status"
            )

        result = repository.get(evidence_id)

        if result:
            return {
                "anchored": True,
                "blockchain_network": result.get("blockchain_network"),
                "contract_address": result.get("contract_address"),
                "transaction_hash": result.get("transaction_hash"),
                "block_number": result.get("block_number"),
                "anchored_at": result.get("anchored_at"),
            }
        else:
            return {
                "anchored": False,
                "message": "No Ethereum anchor found for this evidence record",
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking evidence anchor status: {str(e)}"
        )
