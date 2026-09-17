"""
Evidence Anchor API endpoints for LexProof.

Provides endpoints for anchoring evidence records to Ethereum and
verifying evidence against blockchain anchors.

SECURITY: Only hashes are stored on-chain. Never stores evidence content,
PII, or sensitive data.
"""

import asyncio
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..services.ethereum_anchor_service import (
    EthereumAnchorService,
    get_ethereum_anchor_service,
)
from ..repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository, FirestoreRepository
from ..config import LexProofSettings, get_settings
from ..services.auth import get_current_user

router = APIRouter(tags=["evidence-anchor"])


def _is_settings_instance(value: Any) -> bool:
    return bool(value) and hasattr(value, "project_id") and hasattr(value, "ethereum_rpc_url")


def _is_repository_instance(value: Any) -> bool:
    return bool(value) and hasattr(value, "get") and hasattr(value, "set") and hasattr(value, "delete")


def _resolve_dependency(value: Any, factory, **kwargs):
    if value is None:
        return factory(**kwargs)
    if hasattr(value, "dependency") and callable(getattr(value, "dependency")):
        return factory(**kwargs)
    return value


def _normalize_anchor_dependencies(user, settings, repository, evidence_records_repository):
    if evidence_records_repository is not None and hasattr(evidence_records_repository, "dependency"):
        evidence_records_repository = None

    if (
        settings is not None
        and _is_repository_instance(settings)
        and repository is not None
        and _is_repository_instance(repository)
        and evidence_records_repository is None
    ):
        evidence_records_repository = repository
        repository = settings
        settings = get_settings()
    elif (
        settings is not None
        and _is_repository_instance(settings)
        and repository is None
        and evidence_records_repository is None
    ):
        repository = settings
        settings = get_settings()

    if settings is None or not _is_settings_instance(settings):
        settings = get_settings()
    if repository is None and evidence_records_repository is not None:
        repository = evidence_records_repository
    if repository is None:
        repository = get_evidence_repository(settings=settings)
    if evidence_records_repository is None:
        evidence_records_repository = get_evidence_records_repository(settings=settings)
    return user, settings, repository, evidence_records_repository


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
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
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
    user: dict[str, Any] = Depends(get_current_user),
    settings: LexProofSettings = Depends(get_settings),
    repository: FirestoreRepository = Depends(get_evidence_repository),
    evidence_records_repository: FirestoreRepository = Depends(get_evidence_records_repository)
) -> EvidenceAnchorResponse:
    user = _resolve_dependency(user, get_current_user)
    user, settings, repository, evidence_records_repository = _normalize_anchor_dependencies(
        user,
        settings,
        repository,
        evidence_records_repository,
    )
    """
    Anchor an evidence record to Ethereum.

    SECURITY: Only the evidence_hash is stored on-chain. Never stores evidence content,
    PII, or sensitive data.

    Args:
        evidence_id: Evidence record identifier
        request: Evidence anchoring request
        user: Current authenticated user (from Firebase)
        settings: LexProof settings (injected)
        repository: Firestore repository (injected)

    Returns:
        Evidence anchor response with transaction details

    Raises:
        HTTPException: If validation fails, authorization fails, or transaction fails
    """
    try:
        if request.evidence_id != evidence_id:
            raise ValueError("Evidence ID in request must match path parameter")

        # Authorization: Verify the user owns this evidence
        evidence = evidence_records_repository.get(evidence_id)
        if not evidence:
            raise ValueError(f"Evidence record not found for evidence_id: {evidence_id}")

        if isinstance(user, dict) and "uid" in user and evidence.get("owner_id") != str(user["uid"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User {user['uid']} is not authorized to anchor evidence {evidence_id}"
            )

        # Initialize services. get_ethereum_anchor_service() is a lazy singleton
        # accessor: on its first call per process it constructs a real
        # BlockchainService, which does blocking network I/O (connectivity
        # check + an eth_chainId RPC call) -- run that construction on a worker
        # thread so it can never stall the event loop (hardening item #2; see
        # ethereum_anchor_service.py's get_ethereum_anchor_service for the full
        # rationale). Every call after the first just returns the cached
        # instance, so this is cheap on the common path too.
        anchor_service = await asyncio.to_thread(
            get_ethereum_anchor_service,
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

    except HTTPException:
        raise
    except ValueError as e:
        if str(e).startswith("Evidence record not found"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        if "pending" in str(e).lower() or "confirmation unavailable" in str(e).lower() or "temporarily unavailable" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Ethereum anchoring is temporarily unavailable: {str(e)}"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        if "pending" in str(e).lower() or "confirmation unavailable" in str(e).lower() or "temporarily unavailable" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Ethereum anchoring is temporarily unavailable: {str(e)}"
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error anchoring evidence to Ethereum: {str(e)}"
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error anchoring evidence to Ethereum: {str(e)}"
        ) from e


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
    settings = _resolve_dependency(settings, get_settings)
    _, settings, repository, _ = _normalize_anchor_dependencies(None, settings, repository, None)
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
        # Retrieve anchor from repository
        # (No blockchain service is constructed here - this route only ever reads
        # the persisted anchor record from Firestore, but used to build a full
        # EthereumAnchorService (and, inside it, a BlockchainService that can do
        # real RPC I/O) and then never use the result. That's dead code, and on a
        # page with several evidence items this route fires once per item
        # concurrently - the wasted construction cost was serializing on the
        # single event loop and stalling every other request behind it.)
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
    _, settings, repository, evidence_records_repository = _normalize_anchor_dependencies(
        None,
        settings,
        repository,
        evidence_records_repository,
    )
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
        # Initialize service. See the matching comment in
        # anchor_evidence_to_blockchain() above -- same lazy-singleton
        # construction, same reason it must run off the event loop.
        anchor_service = await asyncio.to_thread(
            get_ethereum_anchor_service,
            settings=settings,
            repository=repository,
            evidence_repository=evidence_records_repository,
        )

        # Verify evidence
        result = await anchor_service.verify_evidence(
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
