"""
Blockchain API endpoints for LexProof
"""

from typing import Any, Dict, List, Optional
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from datetime import datetime
import json
import os
import hashlib

from ..services.blockchain import BlockchainService, TransactionStatus, create_blockchain_service
from ..services.ethereum_anchor_service import get_ethereum_anchor_service
from ..repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository, FirestoreRepository
from ..services.version_comparison import VersionComparisonEngine
from ..config import get_settings

router = APIRouter(tags=["blockchain"])
# No prefix here -- this router is mounted as its own wildcard-CORS
# sub-application at exactly "/api/verify" in main.py (the embeddable
# public-verification widget needs a fully open CORS policy that the rest
# of the API must not share), so the mount path itself supplies the
# "/verify" segment and this router only needs its route's own suffix.
public_verify_router = APIRouter(tags=["public-verification"])
# Contract Time Machine Router
time_machine_router = APIRouter(tags=["contract-time-machine"], prefix="/time-machine")


# Pydantic models
class ProofAnchoringRequest(BaseModel):
    """Request model for proof anchoring"""
    contract_id: str = Field(..., description="Contract ID")
    contract_hash: str = Field(..., description="SHA-256 hash of contract")
    policy_hash: str = Field(..., description="SHA-256 hash of policy")
    analysis_hash: str = Field(..., description="SHA-256 hash of analysis")
    evidence_hash: str = Field(..., description="SHA-256 hash of evidence")
    risk_score: int = Field(..., ge=0, le=100, description="Risk score (0-100)")
    compliance_score: int = Field(..., ge=0, le=100, description="Compliance score (0-100)")
    policy_version: str = Field(..., description="Policy version")
    evidence_count: int = Field(..., ge=1, description="Number of evidence items")
    max_fee_per_gas: Optional[int] = Field(None, description="Max fee per gas for EIP-1559")
    max_priority_fee_per_gas: Optional[int] = Field(None, description="Max priority fee per gas for EIP-1559")


class ProofVerificationRequest(BaseModel):
    """Request model for proof verification"""
    proof_id: str = Field(..., description="Proof ID on blockchain")
    contract_hash: str = Field(..., description="Contract hash to verify")
    policy_hash: str = Field(..., description="Policy hash to verify")
    analysis_hash: str = Field(..., description="Analysis hash to verify")
    evidence_hash: str = Field(..., description="Evidence hash to verify")


class ProofAnchoringResponse(BaseModel):
    """Response model for proof anchoring"""
    proof_id: str
    transaction_hash: str
    block_number: int
    status: str
    timestamp: datetime
    network: str
    contract_address: str


class ProofVerificationResponse(BaseModel):
    """Response model for proof verification"""
    proof_id: str
    is_valid: bool
    status: str
    timestamp: datetime


class ProofDetailsResponse(BaseModel):
    """Response model for proof details"""
    contract_hash: str
    policy_hash: str
    analysis_hash: str
    evidence_hash: str
    risk_score: int
    compliance_score: int
    policy_version: str
    evidence_count: int
    timestamp: int
    registered_by: str
    status: str


class TransactionDetailsResponse(BaseModel):
    """Response model for transaction details"""
    proof_id: str
    transaction_hash: str
    block_number: int
    timestamp: int


# In-memory storage for transaction status (in production, use a proper database)
class TransactionStore:
    """In-memory transaction store for tracking status"""
    def __init__(self, repository: Optional[FirestoreRepository] = None):
        self.transactions = {}
        self.repository = repository
    
    def add_transaction(self, proof_id: str, tx_hash: str, block_number: int):
        """Add transaction to store"""
        transaction = {
            'proof_id': proof_id,
            'transaction_hash': tx_hash,
            'block_number': block_number,
            'status': TransactionStatus.PENDING,
            'timestamp': datetime.now()
        }
        self.transactions[proof_id] = transaction
        if self.repository:
            self.repository.set(proof_id, {
                **transaction,
                "status": TransactionStatus.PENDING.value,
                "timestamp": transaction["timestamp"].isoformat(),
            })
    
    def update_status(self, proof_id: str, status: str):
        """Update transaction status"""
        if proof_id in self.transactions:
            self.transactions[proof_id]['status'] = status
            if self.repository:
                self.repository.set(proof_id, {"status": status}, merge=True)
    
    def get_transaction(self, proof_id: str) -> Optional[dict]:
        """Get transaction from store"""
        transaction = self.transactions.get(proof_id)
        if transaction is None and self.repository:
            transaction = self.repository.get(proof_id)
            if transaction:
                transaction["timestamp"] = datetime.fromisoformat(transaction["timestamp"])
        return transaction


# Initialize transaction store
transaction_store = TransactionStore(
    FirestoreRepository("blockchain_proofs")
    if os.getenv("BLOCKCHAIN_PERSISTENCE", "memory").lower() == "firestore"
    else None
)


def verify_proof_on_chain(
    proof_id: str,
    contract_hash: str,
    policy_hash: str,
    analysis_hash: str,
    evidence_hash: str
) -> bool:
    """
    Verify proof on blockchain
    
    Args:
        proof_id: Proof ID
        contract_hash: Contract hash
        policy_hash: Policy hash
        analysis_hash: Analysis hash
        evidence_hash: Evidence hash
        
    Returns:
        True if valid, False otherwise
    """
    blockchain = create_blockchain_service()
    
    try:
        # Convert hex strings to bytes
        contract_hash_bytes = bytes.fromhex(contract_hash.replace('0x', ''))
        policy_hash_bytes = bytes.fromhex(policy_hash.replace('0x', ''))
        analysis_hash_bytes = bytes.fromhex(analysis_hash.replace('0x', ''))
        evidence_hash_bytes = bytes.fromhex(evidence_hash.replace('0x', ''))
        
        # Verify proof
        is_valid = blockchain.verify_proof(
            bytes.fromhex(proof_id),
            contract_hash_bytes,
            policy_hash_bytes,
            analysis_hash_bytes,
            evidence_hash_bytes
        )
        
        return is_valid
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying proof: {str(e)}"
        )


# Public Verification Endpoint
class VerificationRequest(BaseModel):
    """Request model for public verification"""
    document_content: str = Field(..., description="Document content to verify")
    passport_id: Optional[str] = Field(None, description="Passport ID (optional for blockchain verification)")


class EvidencePublicVerificationResult(BaseModel):
    """Response model for public evidence verification.

    Recomputes the evidence hash from the stored evidence record and compares
    it against the hash anchored on Ethereum. Never exposes evidence content,
    title, or any other private contract data - hashes and chain metadata only.
    """
    evidence_id: str
    verified: bool
    status: str
    evidence_hash_on_chain: Optional[str] = None
    computed_hash: Optional[str] = None
    blockchain_network: Optional[str] = None
    contract_address: Optional[str] = None
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    anchored_at: Optional[str] = None
    timestamp: datetime


@router.post(
    "/passports/{passport_id}/anchor",
    response_model=ProofAnchoringResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Anchor proof to blockchain"
)
async def anchor_proof_to_blockchain(
    passport_id: str,
    request: ProofAnchoringRequest,
    background_tasks: BackgroundTasks
) -> ProofAnchoringResponse:
    """
    Anchor a legal passport proof to Ethereum Sepolia blockchain
    
    SECURITY: Only hashes and non-sensitive metadata are stored on-chain.
    Never stores contract content, PII, contract text, or AI findings.
    
    Args:
        passport_id: Legal passport ID
        request: Proof anchoring request with hashes and scores
        background_tasks: Background tasks for async verification
        
    Returns:
        Proof anchoring response with transaction details
    """
    try:
        # Convert hex strings to bytes
        contract_hash_bytes = bytes.fromhex(request.contract_hash.replace('0x', ''))
        policy_hash_bytes = bytes.fromhex(request.policy_hash.replace('0x', ''))
        analysis_hash_bytes = bytes.fromhex(request.analysis_hash.replace('0x', ''))
        evidence_hash_bytes = bytes.fromhex(request.evidence_hash.replace('0x', ''))

        # Blockchain service construction (RPC round-trip) and the register_proof
        # transaction (submit + wait for receipt) are both blocking web3.py calls;
        # run them on a worker thread so they don't stall the event loop and, with
        # it, every other request (see status-and-plan.md §2c/§11f).
        def _register_proof_sync():
            blockchain = create_blockchain_service()
            proof_id = blockchain.proof_id_for_hashes(
                contract_hash_bytes, policy_hash_bytes, analysis_hash_bytes, evidence_hash_bytes
            ).hex()
            tx_hash, block_number = blockchain.register_proof(
                contract_hash=contract_hash_bytes,
                policy_hash=policy_hash_bytes,
                analysis_hash=analysis_hash_bytes,
                evidence_hash=evidence_hash_bytes,
                risk_score=request.risk_score,
                compliance_score=request.compliance_score,
                policy_version=request.policy_version,
                evidence_count=request.evidence_count,
                max_fee_per_gas=request.max_fee_per_gas,
                max_priority_fee_per_gas=request.max_priority_fee_per_gas
            )
            return blockchain, proof_id, tx_hash, block_number

        blockchain, proof_id, tx_hash, block_number = await asyncio.to_thread(_register_proof_sync)
        
        # Store transaction status
        transaction_store.add_transaction(proof_id, tx_hash, block_number)
        transaction_store.update_status(proof_id, TransactionStatus.CONFIRMED.value)
        
        # Add background task to verify transaction
        background_tasks.add_task(
            verify_proof_on_chain,
            proof_id,
            request.contract_hash,
            request.policy_hash,
            request.analysis_hash,
            request.evidence_hash
        )
        
        return ProofAnchoringResponse(
            proof_id=proof_id,
            transaction_hash=tx_hash,
            block_number=block_number,
            status=TransactionStatus.CONFIRMED.value,
            timestamp=datetime.now(),
            network="ethereum-sepolia",
            contract_address=blockchain.contract_address
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error anchoring proof: {str(e)}"
        )


@router.get(
    "/passports/{passport_id}/proof",
    response_model=ProofDetailsResponse,
    summary="Get proof details from blockchain"
)
async def get_proof_from_blockchain(passport_id: str) -> ProofDetailsResponse:
    """
    Get proof details from blockchain
    
    Args:
        passport_id: Legal passport ID
        
    Returns:
        Proof details including hashes, scores, and metadata
    """
    try:
        # Convert proof_id to bytes
        proof_id_bytes = bytes.fromhex(passport_id)

        def _get_proof_sync():
            blockchain = create_blockchain_service()
            return blockchain.get_proof(proof_id_bytes)

        proof_details = await asyncio.to_thread(_get_proof_sync)

        return ProofDetailsResponse(**proof_details)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting proof: {str(e)}"
        )


@router.get(
    "/proofs/{proof_id}/verify",
    response_model=ProofVerificationResponse,
    summary="Verify proof on blockchain"
)
async def verify_proof(
    proof_id: str,
    contract_hash: str,
    policy_hash: str,
    analysis_hash: str,
    evidence_hash: str
) -> ProofVerificationResponse:
    """
    Verify a proof on blockchain by comparing hashes
    
    Args:
        proof_id: Proof ID on blockchain
        contract_hash: Contract hash to verify
        policy_hash: Policy hash to verify
        analysis_hash: Analysis hash to verify
        evidence_hash: Evidence hash to verify
        
    Returns:
        Verification result
    """
    try:
        is_valid = await asyncio.to_thread(
            verify_proof_on_chain,
            proof_id,
            contract_hash,
            policy_hash,
            analysis_hash,
            evidence_hash
        )
        
        return ProofVerificationResponse(
            proof_id=proof_id,
            is_valid=is_valid,
            status="verified",
            timestamp=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying proof: {str(e)}"
        )


@router.get(
    "/proofs/{proof_id}/transaction",
    response_model=TransactionDetailsResponse,
    summary="Get transaction details for proof"
)
async def get_transaction_details(proof_id: str) -> TransactionDetailsResponse:
    """
    Get transaction details for a proof
    
    Args:
        proof_id: Proof ID
        
    Returns:
        Transaction details including hash, block number, and timestamp
    """
    try:
        transaction = transaction_store.get_transaction(proof_id)
        if transaction is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction does not exist"
            )
        return TransactionDetailsResponse(
            proof_id=transaction["proof_id"],
            transaction_hash=transaction["transaction_hash"],
            block_number=transaction["block_number"],
            timestamp=int(transaction["timestamp"].timestamp()),
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting transaction: {str(e)}"
        )


@router.get(
    "/health",
    summary="Check blockchain service health"
)
async def check_blockchain_health() -> dict:
    """
    Check blockchain service health
    
    Returns:
        Health status and connection details
    """
    try:
        def _health_check_sync():
            blockchain = create_blockchain_service()
            return blockchain, blockchain.get_current_block_number()

        blockchain, block_number = await asyncio.to_thread(_health_check_sync)

        return {
            "status": "healthy",
            "network": "ethereum-sepolia",
            "chain_id": blockchain.chain_id,
            "contract_address": blockchain.contract_address,
            "current_block": block_number
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Blockchain service unhealthy: {str(e)}"
        )


@public_verify_router.get(
    "/{evidence_id}",
    response_model=EvidencePublicVerificationResult,
    summary="Public evidence verification portal"
)
async def public_verify_evidence(evidence_id: str) -> EvidencePublicVerificationResult:
    """
    Public verification portal - no authentication required.

    Recomputes the evidence hash from the evidence record stored in Firestore
    (the exact same canonicalization used when the evidence was anchored) and
    compares it against the hash anchored on Ethereum. This is real
    cryptographic + on-chain verification, not a database lookup: if the
    stored evidence has been altered since anchoring, the recomputed hash
    will not match the on-chain hash and status will be TAMPERED.

    SECURITY: Never exposes evidence content, title, or any other private
    contract data. Only hashes and chain metadata are returned.

    Args:
        evidence_id: Evidence record identifier to verify

    Returns:
        Verification result: VERIFIED, TAMPERED, EVIDENCE_NOT_FOUND, or ANCHOR_NOT_FOUND
    """
    if not evidence_id or not evidence_id.strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence ID is required"
        )

    try:
        settings = get_settings()
        anchor_repository = EvidenceAnchorRepository("evidence_anchors", settings=settings)
        evidence_records_repository = EvidenceRecordRepository(anchor_repository, settings=settings)
        # get_ethereum_anchor_service() is a lazy singleton accessor: on its
        # first call per process it constructs a real BlockchainService, which
        # does blocking network I/O (connectivity check + an eth_chainId RPC
        # call) -- run that construction on a worker thread so it can never
        # stall the event loop, including on this public, unauthenticated
        # endpoint (hardening item #2; see ethereum_anchor_service.py's
        # get_ethereum_anchor_service for the full rationale). Every call
        # after the first just returns the cached instance, so this is cheap
        # on the common path too.
        anchor_service = await asyncio.to_thread(
            get_ethereum_anchor_service,
            settings=settings,
            repository=anchor_repository,
            evidence_repository=evidence_records_repository,
        )

        result = await anchor_service.verify_evidence(evidence_id)

        return EvidencePublicVerificationResult(
            evidence_id=evidence_id,
            verified=result.get("verified", False),
            status=result.get("status", "UNKNOWN"),
            evidence_hash_on_chain=result.get("evidence_hash_on_chain"),
            computed_hash=result.get("computed_hash"),
            blockchain_network=result.get("blockchain_network"),
            contract_address=result.get("contract_address"),
            transaction_hash=result.get("transaction_hash"),
            block_number=result.get("block_number"),
            anchored_at=result.get("anchored_at"),
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying evidence: {str(e)}"
        )


# Pydantic models for Contract Time Machine
class VersionComparisonRequest(BaseModel):
    """Request model for version comparison"""
    contract_id: str = Field(..., description="Contract identifier")
    version_from: int = Field(..., description="Previous version number")
    version_to: int = Field(..., description="Current version number")


class VersionComparisonResponse(BaseModel):
    """Response model for version comparison"""
    contract_id: str
    version_from: int
    version_to: int
    total_clauses: int
    unchanged_clauses: int
    added_clauses: int
    removed_clauses: int
    modified_clauses: int
    clause_changes: List[Dict[str, Any]]
    risk_delta: float
    compliance_delta: float
    policy_delta: str
    business_impact: str
    blockchain_proof_verified: bool


class VersionHistoryResponse(BaseModel):
    """Response model for version history"""
    contract_id: str
    versions: List[Dict[str, Any]]


class VersionVerificationRequest(BaseModel):
    """Request model for verifying version against blockchain"""
    passport_id: str = Field(..., description="Passport ID to verify")


class VersionVerificationResponse(BaseModel):
    """Response model for version verification"""
    passport_id: str
    is_verified: bool
    verification_status: str
    blockchain_proof_status: str
    timestamp: datetime


# Initialize version comparison engine
version_comparison_engine = VersionComparisonEngine()


@time_machine_router.get(
    "/compare",
    response_model=VersionComparisonResponse,
    summary="Compare two contract versions"
)
async def compare_contract_versions(
    contract_id: str,
    version_from: int,
    version_to: int
) -> VersionComparisonResponse:
    """
    Compare two contract versions and detect changes

    Detects:
    - Added clauses
    - Removed clauses
    - Modified clauses
    - Unchanged clauses

    Calculates:
    - Risk delta
    - Compliance delta
    - Business impact
    - Policy changes

    Args:
        contract_id: Contract identifier
        version_from: Previous version number
        version_to: Current version number

    Returns:
        VersionComparison with all changes and deltas
    """
    try:
        # This is a demo implementation
        # In production, you would:
        # 1. Retrieve previous version's clauses from database
        # 2. Retrieve current version's clauses from database
        # 3. Compare using VersionComparisonEngine
        # 4. Return comparison results

        # Demo: Return sample comparison data
        # In production, replace with actual database queries

        # Simulate clause comparison
        # (In production, retrieve actual clauses from storage)
        previous_clauses = [
            Clause(
                text="Clause 1: Party A shall pay on time.",
                hash="hash1",
                risk_score=30.0,
                compliance_score=80.0
            ),
            Clause(
                text="Clause 2: Confidentiality obligations.",
                hash="hash2",
                risk_score=20.0,
                compliance_score=90.0
            ),
            Clause(
                text="Clause 3: Termination rights.",
                hash="hash3",
                risk_score=40.0,
                compliance_score=70.0
            )
        ]

        current_clauses = [
            Clause(
                text="Clause 1: Party A shall pay on time.",
                hash="hash1",
                risk_score=30.0,
                compliance_score=80.0
            ),
            Clause(
                text="Clause 2: Confidentiality obligations.",
                hash="hash2",
                risk_score=25.0,
                compliance_score=95.0
            ),
            Clause(
                text="Clause 4: NEW Clause added.",
                hash="hash4",
                risk_score=15.0,
                compliance_score=100.0
            )
        ]

        # Perform comparison
        comparison = version_comparison_engine.compare_versions(
            contract_id=contract_id,
            version_from=version_from,
            version_to=version_to,
            previous_clauses=previous_clauses,
            current_clauses=current_clauses,
            previous_policy_version=f"Policy-{version_from}",
            current_policy_version=f"Policy-{version_to}",
            previous_risk_score=30.0,
            current_risk_score=28.0,
            previous_compliance_score=80.0,
            current_compliance_score=88.0
        )

        # Get summary
        summary = version_comparison_engine.get_summary(comparison)
        changes = version_comparison_engine.get_clause_change_details(comparison)

        return VersionComparisonResponse(
            contract_id=summary["contract_id"],
            version_from=summary["version_from"],
            version_to=summary["version_to"],
            total_clauses=summary["total_clauses"],
            unchanged_clauses=summary["unchanged"],
            added_clauses=summary["added"],
            removed_clauses=summary["removed"],
            modified_clauses=summary["modified"],
            clause_changes=changes,
            risk_delta=summary["risk_delta"],
            compliance_delta=summary["compliance_delta"],
            policy_delta=summary["policy_delta"],
            business_impact=summary["business_impact"],
            blockchain_proof_verified=summary["blockchain_proof_verified"]
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error comparing versions: {str(e)}"
        )


@time_machine_router.get(
    "/history/{contract_id}",
    response_model=VersionHistoryResponse,
    summary="Get version history for a contract"
)
async def get_version_history(contract_id: str) -> VersionHistoryResponse:
    """
    Get version history for a contract

    Args:
        contract_id: Contract identifier

    Returns:
        List of versions with their details
    """
    try:
        # This is a demo implementation
        # In production, you would:
        # 1. Query database for all versions of the contract
        # 2. Retrieve blockchain proof status for each version
        # 3. Return version history

        # Demo: Return sample version history
        versions = [
            {
                "version": 1,
                "contract_id": contract_id,
                "document_hash": "0xabc123...",
                "policy_hash": "0xdef456...",
                "analysis_hash": "0xghi789...",
                "evidence_hash": "0xjkl012...",
                "risk_score": 30.0,
                "compliance_score": 80.0,
                "policy_version": "Policy-1",
                "created_at": "2024-09-23T10:00:00",
                "blockchain_proof_status": "verified",
                "transaction_hash": "0x123456...",
                "block_number": 12345678
            },
            {
                "version": 2,
                "contract_id": contract_id,
                "document_hash": "0xabc124...",
                "policy_hash": "0xdef457...",
                "analysis_hash": "0xghi790...",
                "evidence_hash": "0xjkl013...",
                "risk_score": 28.0,
                "compliance_score": 88.0,
                "policy_version": "Policy-2",
                "created_at": "2024-09-24T10:00:00",
                "blockchain_proof_status": "verified",
                "transaction_hash": "0x234567...",
                "block_number": 12356789
            },
            {
                "version": 3,
                "contract_id": contract_id,
                "document_hash": "0xabc125...",
                "policy_hash": "0xdef458...",
                "analysis_hash": "0xghi791...",
                "evidence_hash": "0xjkl014...",
                "risk_score": 35.0,
                "compliance_score": 75.0,
                "policy_version": "Policy-3",
                "created_at": "2024-09-25T10:00:00",
                "blockchain_proof_status": "pending",
                "transaction_hash": None,
                "block_number": None
            },
            {
                "version": 4,
                "contract_id": contract_id,
                "document_hash": "0xabc126...",
                "policy_hash": "0xdef459...",
                "analysis_hash": "0xghi792...",
                "evidence_hash": "0xjkl015...",
                "risk_score": 32.0,
                "compliance_score": 82.0,
                "policy_version": "Policy-4",
                "created_at": "2024-09-26T10:00:00",
                "blockchain_proof_status": "not_anchored",
                "transaction_hash": None,
                "block_number": None
            }
        ]

        return VersionHistoryResponse(
            contract_id=contract_id,
            versions=versions
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting version history: {str(e)}"
        )


@time_machine_router.post(
    "/verify-version",
    response_model=VersionVerificationResponse,
    summary="Verify version against blockchain proof"
)
async def verify_version_against_blockchain(
    request: VersionVerificationRequest
) -> VersionVerificationResponse:
    """
    Verify a version's blockchain proof

    Args:
        request: Passport ID to verify

    Returns:
        Verification status and blockchain proof status
    """
    try:
        # This is a demo implementation
        # In production, you would:
        # 1. Retrieve passport from database
        # 2. Get blockchain proof for the passport
        # 3. Verify the proof on-chain
        # 4. Return verification status

        # Demo: Return sample verification result
        return VersionVerificationResponse(
            passport_id=request.passport_id,
            is_verified=True,
            verification_status="VERIFIED",
            blockchain_proof_status="PROOF_CONFIRMED_ON_BLOCKCHAIN",
            timestamp=datetime.now()
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying version: {str(e)}"
        )
