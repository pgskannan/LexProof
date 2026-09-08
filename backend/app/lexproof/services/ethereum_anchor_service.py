"""
Ethereum Anchor Service for LexProof evidence records.

This service provides evidence-level anchoring to Ethereum using the existing
BlockchainService infrastructure. It reuses the LexProofRegistry smart contract
and does not duplicate blockchain logic.

SECURITY: All credentials are loaded from environment variables or Secret Manager.
Never stores private keys in source code or configuration files.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncio
import logging
import re

from ..services.blockchain import BlockchainService, create_blockchain_service
from ..repositories.firestore import FirestoreRepository
from ..config import LexProofSettings, get_settings
from ..domains.passport.utils.hashing import hash_evidence_item

logger = logging.getLogger(__name__)
HASH_PATTERN = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")


class EthereumAnchorService:
    """
    Service for anchoring evidence records to Ethereum.

    This service:
    1. Validates evidence hashes
    2. Checks for duplicate anchors
    3. Submits hashes to LexProofRegistry contract
    4. Persists blockchain proof metadata
    5. Provides verification capability

    Uses existing BlockchainService infrastructure - no new blockchain client.
    """

    def __init__(
        self,
        settings: Optional[LexProofSettings] = None,
        repository: Optional[FirestoreRepository] = None,
        evidence_repository: Optional[FirestoreRepository] = None,
    ):
        """
        Initialize Ethereum anchor service.

        Args:
            settings: LexProof settings (loads from env if None)
            repository: Firestore repository for persistence (optional)
        """
        self.settings = settings or get_settings()
        self.repository = repository
        self.evidence_repository = evidence_repository
        self.blockchain = create_blockchain_service(
            rpc_url=self.settings.ethereum_rpc_url,
            contract_address=self.settings.contract_address,
            private_key=self.settings.blockchain_private_key.get_secret_value(),
        )

    async def anchor_evidence(
        self,
        evidence_id: str,
    ) -> Dict[str, Any]:
        """
        Anchor an evidence record to Ethereum.

        This method is idempotent and supports recovery from distributed failures:
        - If Firestore record exists, validates and returns it
        - If Firestore missing, checks Ethereum for existing anchor
        - If Ethereum has anchor, recovers and persists metadata
        - If no Ethereum anchor, submits new transaction

        Args:
            evidence_id: Evidence record identifier
        Returns:
            Dictionary containing blockchain proof details

        Raises:
            ValueError: If validation fails or transaction fails
        """
        self._validate_record_id(evidence_id)
        if not self.repository or not self.evidence_repository:
            raise ValueError("Evidence and evidence anchor repositories are required")
        evidence = self.evidence_repository.get(evidence_id)
        if not evidence:
            raise ValueError(f"Evidence record not found for evidence_id: {evidence_id}")
        passport_id = evidence.get("passport_id")
        self._validate_record_id(passport_id)
        evidence_hash = hash_evidence_item(evidence)
        existing = self.repository.get(evidence_id)
        if existing:
            if existing.get("evidence_hash", "").lower() != evidence_hash.lower():
                raise ValueError("Evidence already has a different Ethereum anchor")
            return existing

        # Check Ethereum for existing anchor (recovery path for distributed failures)
        recovered = await self._recover_from_chain_if_anchored(evidence_id, passport_id, evidence_hash)
        if recovered is not None:
            return recovered

        # No Ethereum anchor exists yet, submit a new transaction.
        try:
            tx_hash, block_number, anchored_timestamp = await asyncio.to_thread(
                self.blockchain.anchor_evidence, evidence_id, bytes.fromhex(evidence_hash)
            )
        except Exception as exc:
            # The submission itself can fail because a concurrent caller (e.g. a
            # retried analyze request, or two requests racing after a prior
            # transient failure) already anchored this exact evidence_id in the
            # window between our on-chain check above and this transaction being
            # built and sent - gas estimation or the transaction then reverts
            # against the now-updated contract state. Re-check Ethereum once more
            # before giving up: if the anchor is there now, this was that race and
            # we should recover the now-confirmed anchor instead of failing.
            recovered = await self._recover_from_chain_if_anchored(evidence_id, passport_id, evidence_hash)
            if recovered is not None:
                logger.warning(
                    "Ethereum anchor submission for evidence_id=%s failed (%s) but a matching "
                    "anchor was found on-chain afterward; recovering instead of failing.",
                    evidence_id, exc,
                )
                return recovered
            raise

        blockchain_proof = {
            "evidence_id": evidence_id,
            "passport_id": passport_id,
            "blockchain_network": "ethereum-sepolia",
            "contract_address": self.blockchain.contract_address,
            "transaction_hash": tx_hash,
            "block_number": block_number,
            "anchored_at": datetime.fromtimestamp(anchored_timestamp, timezone.utc).isoformat(),
            "evidence_hash": evidence_hash,
            # Discriminator for anchoring strategy. Every real anchor submitted through
            # this method is a direct single-hash anchor; a batched (Merkle-root)
            # anchoring strategy is a documented future direction (see
            # hackathon-polish-roadmap.md), demonstrated via a hand-crafted mock
            # record (scripts/create_merkle_batch_demo_anchor.py), never through this
            # code path. This field is purely additive and does not change what gets
            # submitted on-chain or how existing anchors are read.
            "anchoring_method": "SINGLE_HASH",
        }
        self._create_anchor(evidence_id, blockchain_proof)

        return blockchain_proof

    async def _recover_from_chain_if_anchored(
        self, evidence_id: str, passport_id: str, evidence_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Check Ethereum for an anchor matching evidence_hash and recover it if found.

        Returns None (without raising) when no anchor exists on-chain yet - callers
        should treat that as "still need to submit a new transaction". Raises
        ValueError only when Ethereum already has a *different*, conflicting anchor
        for this evidence_id, since that is a genuine data-integrity problem rather
        than a race to recover from.
        """
        on_chain = await asyncio.to_thread(self.blockchain.get_evidence_anchor, evidence_id)
        if not on_chain:
            return None
        if on_chain.get("evidence_hash", "").lower().removeprefix("0x") != evidence_hash.lower():
            raise ValueError(
                f"Evidence already has a different Ethereum anchor with hash {on_chain.get('evidence_hash', 'unknown')}"
            )
        # Ethereum has the anchor, recover and persist metadata using the event log's
        # actual transaction hash rather than the evidence hash itself.
        tx_hash_value = await asyncio.to_thread(
            self.blockchain.get_anchor_transaction_hash, evidence_id, on_chain["evidence_hash"]
        )
        tx_hash, block_number, anchored_timestamp = await asyncio.to_thread(
            self.blockchain.recover_confirmed_transaction, tx_hash_value
        )
        blockchain_proof = {
            "evidence_id": evidence_id,
            "passport_id": passport_id,
            "blockchain_network": "ethereum-sepolia",
            "contract_address": self.blockchain.contract_address,
            "transaction_hash": tx_hash,
            "block_number": block_number,
            "anchored_at": datetime.fromtimestamp(anchored_timestamp, timezone.utc).isoformat(),
            "evidence_hash": evidence_hash,
            "anchoring_method": "SINGLE_HASH",
        }
        self._create_anchor(evidence_id, blockchain_proof)
        return blockchain_proof

    async def verify_evidence(
        self,
        evidence_id: str,
    ) -> Dict[str, Any]:
        """
        Verify an evidence record against Ethereum anchor.

        Args:
            evidence_id: Evidence record identifier
        Returns:
            Dictionary containing verification result

        Raises:
            ValueError: If anchor not found or verification fails
        """
        self._validate_record_id(evidence_id)
        if not self.repository or not self.evidence_repository:
            raise ValueError("Evidence and evidence anchor repositories are required")
        evidence = self.evidence_repository.get(evidence_id)
        if not evidence:
            return {
                "verified": False,
                "status": "EVIDENCE_NOT_FOUND",
                "message": "Evidence record not found",
                "evidence_hash_on_chain": None,
                "computed_hash": None,
                "blockchain_network": None,
                "contract_address": None,
                "transaction_hash": None,
                "block_number": None,
                "anchored_at": None,
            }
        computed_hash = hash_evidence_item(evidence)
        blockchain_proof = self.repository.get(evidence_id)
        if not blockchain_proof:
            return {
                "verified": False,
                "status": "ANCHOR_NOT_FOUND",
                "message": "No Ethereum anchor found for this evidence record",
                "evidence_hash_on_chain": None,
                "computed_hash": computed_hash,
                "blockchain_network": None,
                "contract_address": None,
                "transaction_hash": None,
                "block_number": None,
                "anchored_at": None,
            }

        on_chain = await asyncio.to_thread(self.blockchain.get_evidence_anchor, evidence_id)
        hashes_match = await asyncio.to_thread(
            self.blockchain.verify_evidence, evidence_id, bytes.fromhex(computed_hash)
        )

        result = {
            "verified": hashes_match,
            "status": "VERIFIED" if hashes_match else "TAMPERED",
            "evidence_hash_on_chain": on_chain["evidence_hash"],
            "computed_hash": computed_hash,
            "blockchain_network": blockchain_proof["blockchain_network"],
            "contract_address": blockchain_proof["contract_address"],
            "transaction_hash": blockchain_proof["transaction_hash"],
            "block_number": blockchain_proof["block_number"],
            "anchored_at": blockchain_proof["anchored_at"],
        }

        if hashes_match:
            logger.info(f"Verified evidence {evidence_id} on Ethereum")
        else:
            logger.warning(
                f"Evidence {evidence_id} verification failed. "
                f"Hash mismatch detected."
            )

        return result

    async def recover_anchor_from_transaction(
        self,
        evidence_id: str,
        transaction_hash: str,
    ) -> Dict[str, Any]:
        """Persist metadata for an already-confirmed transaction without sending."""
        self._validate_record_id(evidence_id)
        if not self.repository or not self.evidence_repository:
            raise ValueError("Evidence and evidence anchor repositories are required")
        evidence = self.evidence_repository.get(evidence_id)
        if not evidence:
            raise ValueError(f"Evidence record not found for evidence_id: {evidence_id}")
        passport_id = evidence.get("passport_id")
        self._validate_record_id(passport_id)
        evidence_hash = hash_evidence_item(evidence)
        existing = self.repository.get(evidence_id)
        if existing:
            if existing.get("evidence_hash", "").lower() != evidence_hash.lower():
                raise ValueError("Evidence already has a different Ethereum anchor")
            if existing.get("transaction_hash", "").lower() != transaction_hash.lower():
                raise ValueError("Evidence already has a different Ethereum anchor")
            return existing

        tx_hash, block_number, anchored_timestamp = await asyncio.to_thread(
            self.blockchain.recover_confirmed_transaction, transaction_hash
        )
        on_chain = await asyncio.to_thread(self.blockchain.get_evidence_anchor, evidence_id)
        if on_chain.get("evidence_hash", "").lower().removeprefix("0x") != evidence_hash:
            raise ValueError("On-chain evidence hash does not match the authoritative evidence record")
        blockchain_proof = {
            "evidence_id": evidence_id,
            "passport_id": passport_id,
            "blockchain_network": "ethereum-sepolia",
            "contract_address": self.blockchain.contract_address,
            "transaction_hash": tx_hash,
            "block_number": block_number,
            "anchored_at": datetime.fromtimestamp(anchored_timestamp, timezone.utc).isoformat(),
            "evidence_hash": evidence_hash,
            "anchoring_method": "SINGLE_HASH",
        }
        self._create_anchor(evidence_id, blockchain_proof)
        return blockchain_proof

    def _create_anchor(self, evidence_id: str, blockchain_proof: Dict[str, Any]) -> None:
        """Persist anchor metadata without allowing replacement or deletion."""
        existing = self.repository.get(evidence_id)
        if existing:
            if existing.get("evidence_hash", "").lower() != blockchain_proof["evidence_hash"].lower():
                raise ValueError("Evidence already has a different Ethereum anchor")
            return
        self.repository.set(evidence_id, blockchain_proof)

    def _validate_evidence_hash(self, evidence_hash: str) -> None:
        """Validate evidence hash format."""
        if not isinstance(evidence_hash, str) or not HASH_PATTERN.fullmatch(evidence_hash):
            raise ValueError("Evidence hash must be a 64-character hexadecimal SHA-256 hash")

    @staticmethod
    def _validate_record_id(record_id: str) -> None:
        if not isinstance(record_id, str) or not record_id.strip() or len(record_id) > 256:
            raise ValueError("Record ID must be between 1 and 256 characters")


# Global instance (lazy loaded)
_ethereum_anchor_service: Optional[EthereumAnchorService] = None


def get_ethereum_anchor_service(
    settings: Optional[LexProofSettings] = None,
    repository: Optional[FirestoreRepository] = None,
    evidence_repository: Optional[FirestoreRepository] = None,
) -> EthereumAnchorService:
    """
    Get or create Ethereum anchor service instance.

    Args:
        settings: LexProof settings (optional)
        repository: Firestore repository (optional)

    Returns:
        EthereumAnchorService instance
    """
    global _ethereum_anchor_service

    if _ethereum_anchor_service is None:
        _ethereum_anchor_service = EthereumAnchorService(
            settings=settings,
            repository=repository,
            evidence_repository=evidence_repository,
        )
    else:
        if repository is not None:
            _ethereum_anchor_service.repository = repository
        if evidence_repository is not None:
            _ethereum_anchor_service.evidence_repository = evidence_repository

    return _ethereum_anchor_service
