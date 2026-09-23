"""Passport Root Anchor Service for LexProof Legal Passports.

Implements the APPROVED design in docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md
(Option D): an additive Sepolia commitment of the existing v1
``metadata.passport_hash`` root, keyed by ``keccak256(bytes(passport_id))``,
on a dedicated ``LexProofPassportRegistry`` contract/address that is fully
independent of the existing per-evidence-item ``LexProofRegistry``.

This service:
  1. Never trusts a client-supplied hash. It recomputes passport integrity
     server-side (``verify_passport_integrity``) from the caller-supplied,
     already-authorized passport document (and, when relevant, live evidence)
     and only ever anchors the server-recomputed root.
  2. Refuses to anchor unless ALL of document/policy/analysis/evidence/
     passport_hash status are PASS. UNVERIFIABLE (legacy / evidence-only
     repaired snapshots) is never treated as eligible, and is never silently
     promoted to PASS because a blockchain root exists elsewhere.
  3. Is idempotent and race-safe, following the same playbook as
     ``EthereumAnchorService`` for per-evidence-item anchors: Firestore
     create-once persistence, on-chain recovery before ever assuming failure,
     and "write Firestore only after receipt status == 1".
  4. Never reuses ``registerProof`` / the item ``evidenceAnchors`` mapping.

Authorization (tenant/org visibility for a given passport_id) is NOT this
service's job -- callers (the API layer) must load the passport through the
existing, already-established authorization path (e.g.
``get_read_passport_service(user).get_passport(passport_id)``, the same
helper ``POST /passports/{id}/verify`` already uses) and pass in the
resulting, already-authorized passport document.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..domains.passport.integrity import FAIL, PASS, UNVERIFIABLE
from ..domains.passport.utils.hashing import compute_passport_key, passport_root_bytes32
from ..repositories.firestore import FirestoreRepository, PassportAnchorRepository
from ..config import LexProofSettings, get_settings
from .analysis_safety import sanitize_analysis_error
from .audit import record_audit_event
from .passport_blockchain import PassportBlockchainService, create_passport_blockchain_service

logger = logging.getLogger(__name__)

# The five verify_passport_integrity fields that must all be PASS for a
# passport to be eligible for root anchoring. Order matches the human-readable
# reasons string; not otherwise significant.
_REQUIRED_INTEGRITY_FIELDS = (
    "document_status",
    "policy_status",
    "analysis_status",
    "evidence_status",
    "passport_hash_status",
)

BLOCKCHAIN_NETWORK = "ethereum-sepolia"
CANONICALIZATION_VERSION = 1
HASH_ALGORITHM = "sha256"
ANCHORING_METHOD = "SINGLE_HASH"


class PassportEligibilityError(ValueError):
    """Raised when a passport does not meet the all-PASS anchoring bar."""

    def __init__(self, passport_id: str, integrity: Dict[str, Any], reasons: List[str]):
        self.passport_id = passport_id
        self.integrity = integrity
        self.reasons = reasons
        super().__init__(
            f"Passport {passport_id} is not eligible for root anchoring: {', '.join(reasons)}"
        )


class PassportRootConflictError(ValueError):
    """Raised when a passport already has a DIFFERENT anchored root.

    This is a hard failure by design (see docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md
    section 10/12): a passport root, once anchored, is never overwritten,
    updated, or silently replaced -- whether the conflicting record is found
    in Firestore or read back from the chain itself.
    """


def passport_root_eligibility(integrity: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return (eligible, human-readable failing-component reasons).

    Eligible means every one of document_status / policy_status /
    analysis_status / evidence_status / passport_hash_status is exactly
    "PASS". FAIL and UNVERIFIABLE both block anchoring -- there is no
    "anchor anyway" path for a legacy or partially-unclaimed snapshot.
    """
    reasons = [
        f"{field}={integrity.get(field)}"
        for field in _REQUIRED_INTEGRITY_FIELDS
        if integrity.get(field) != PASS
    ]
    return (not reasons, reasons)


class PassportRootAnchorService:
    """Anchors and verifies Legal Passport ROOT commitments on Sepolia."""

    def __init__(
        self,
        settings: Optional[LexProofSettings] = None,
        repository: Optional[FirestoreRepository] = None,
        blockchain: Optional[PassportBlockchainService] = None,
    ):
        self.settings = settings or get_settings()
        # PassportAnchorRepository by convention, but any FirestoreRepository-shaped
        # object (including a create-once fake in tests) is accepted.
        self.repository = repository
        # Deliberately NOT constructed eagerly (unlike EthereumAnchorService's
        # constructor): building a PassportBlockchainService does blocking
        # network I/O, and a caller checking eligibility for an UNVERIFIABLE
        # or FAIL passport should never need a working chain connection just
        # to receive that answer. It is built lazily on first real chain use,
        # and only ever from a worker thread (see _ensure_blockchain callers).
        self._blockchain = blockchain

    def _ensure_blockchain(self) -> PassportBlockchainService:
        if self._blockchain is None:
            self._blockchain = create_passport_blockchain_service()
        return self._blockchain

    # ------------------------------------------------------------------
    # Anchoring
    # ------------------------------------------------------------------

    async def anchor_passport_root(
        self,
        passport_id: str,
        passport_doc: Dict[str, Any],
        integrity: Dict[str, Any],
        *,
        actor_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Anchor a passport's root commitment. Idempotent and race-safe.

        ``integrity`` must be the result of calling
        ``domains.passport.integrity.verify_passport_integrity`` on
        ``passport_doc`` -- callers (the API layer) compute it themselves
        (rather than this service recomputing it internally) so there is
        exactly one call site for that recomputation, matching the existing,
        already-tested ``POST /passports/{id}/verify`` code path exactly.
        This service never trusts any OTHER integrity-shaped input: it only
        ever anchors ``integrity["recomputed_passport_hash"]``, which is
        itself derived inside verify_passport_integrity from the passport's
        own STORED component hashes, never from client input.

        Raises:
            PassportEligibilityError: if any required component is not PASS.
            PassportRootConflictError: if a different root is already anchored
                (Firestore or on-chain) for this passport_id.
        """
        self._validate_passport_id(passport_id)
        if not self.repository:
            raise ValueError("Passport anchor repository is required")

        eligible, reasons = passport_root_eligibility(integrity)

        passport_key = compute_passport_key(passport_id)
        audit_context: Dict[str, Any] = {
            "actor_id": actor_id or "system",
            "org_id": org_id,
            "contract_id": passport_doc.get("contract_id"),
            "metadata_base": {
                "passport_id": passport_id,
                "passport_key": passport_key,
            },
        }
        self._audit(
            "passport_root_anchor_requested",
            passport_id,
            audit_context,
            summary=f"Passport root anchoring requested for {passport_id}",
        )

        if not eligible:
            self._audit(
                "passport_root_anchor_failed",
                passport_id,
                audit_context,
                summary=f"Passport root anchoring refused for {passport_id}: not eligible",
                extra_metadata={"reason": "not_eligible", "failing_components": reasons},
            )
            raise PassportEligibilityError(passport_id, integrity, reasons)

        passport_hash = integrity["recomputed_passport_hash"]
        passport_root = passport_root_bytes32(passport_hash)
        passport_key_bytes = bytes.fromhex(passport_key)
        audit_context["metadata_base"]["passport_hash"] = passport_hash

        # Case 1: Firestore already has a (necessarily matching, since this
        # repository is create-once and only ever written after a verified
        # match) anchor for this passport -- idempotent, no transaction.
        existing = self.repository.get(passport_id)
        if existing:
            if existing.get("passport_hash", "").lower() != passport_hash.lower():
                raise PassportRootConflictError(
                    f"Passport {passport_id} already has a different anchored root"
                )
            self._audit(
                "passport_root_anchor_recovered",
                passport_id,
                audit_context,
                summary=f"Passport root anchor already existed for {passport_id}; reused, no new transaction submitted",
                extra_metadata={
                    "transaction_hash": existing.get("transaction_hash"),
                    "block_number": existing.get("block_number"),
                },
            )
            return existing

        blockchain = self._ensure_blockchain()

        # Case 2/3: chain already has this key anchored (a prior Firestore
        # write was lost, or a race with another caller / retry).
        recovered = await self._recover_from_chain_if_anchored(
            passport_id, passport_key, passport_key_bytes, passport_hash, blockchain,
            audit_context=audit_context,
        )
        if recovered is not None:
            return recovered

        # Case 4: submit a new transaction.
        self._audit(
            "passport_root_anchor_submitted",
            passport_id,
            audit_context,
            summary=f"Passport root anchor transaction submitted for {passport_id}",
        )
        try:
            tx_hash, block_number, anchored_timestamp = await asyncio.to_thread(
                blockchain.anchor_passport_root, passport_key_bytes, passport_root
            )
        except Exception as exc:
            # Case 5/race: submission can fail because a concurrent caller
            # already anchored this exact key in the window between our
            # on-chain check above and this transaction being built/sent.
            # Re-check once before giving up, same as EthereumAnchorService.
            recovered = await self._recover_from_chain_if_anchored(
                passport_id, passport_key, passport_key_bytes, passport_hash, blockchain,
                audit_context=audit_context,
            )
            if recovered is not None:
                logger.warning(
                    "Passport root anchor submission for passport_id=%s failed (%s) but a "
                    "matching anchor was found on-chain afterward; recovering instead of failing.",
                    passport_id, exc,
                )
                return recovered
            self._audit(
                "passport_root_anchor_failed",
                passport_id,
                audit_context,
                summary=f"Passport root anchor transaction failed for {passport_id}",
                extra_metadata={"error": sanitize_analysis_error(exc)},
            )
            raise

        anchor_record = self._build_anchor_record(
            passport_id=passport_id,
            passport_hash=passport_hash,
            passport_key=passport_key,
            transaction_hash=tx_hash,
            block_number=block_number,
            anchored_timestamp=anchored_timestamp,
            contract_address=blockchain.contract_address,
        )
        # Write Firestore only after receipt status == 1 (guaranteed above:
        # anchor_passport_root() only returns once the receipt is confirmed).
        self._create_anchor(passport_id, anchor_record)
        self._audit(
            "passport_root_anchor_confirmed",
            passport_id,
            audit_context,
            summary=f"Passport root anchor transaction confirmed for {passport_id}",
            extra_metadata={
                "transaction_hash": tx_hash,
                "block_number": block_number,
            },
        )
        return anchor_record

    async def _recover_from_chain_if_anchored(
        self,
        passport_id: str,
        passport_key: str,
        passport_key_bytes: bytes,
        passport_hash: str,
        blockchain: PassportBlockchainService,
        *,
        audit_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        on_chain = await asyncio.to_thread(blockchain.get_passport_root, passport_key_bytes)
        if not on_chain:
            return None
        on_chain_root = on_chain.get("passport_root", "").lower().removeprefix("0x")
        if on_chain_root != passport_hash.lower():
            raise PassportRootConflictError(
                f"Passport {passport_id} already has a different anchored root on-chain "
                f"({on_chain_root})"
            )

        anchor_record = self._build_anchor_record(
            passport_id=passport_id,
            passport_hash=passport_hash,
            passport_key=passport_key,
            transaction_hash=None,
            block_number=None,
            anchored_timestamp=on_chain["anchored_at"],
            contract_address=blockchain.contract_address,
        )
        try:
            tx_hash_value = await asyncio.to_thread(
                blockchain.get_anchor_transaction_hash, passport_key_bytes, on_chain["passport_root"]
            )
            tx_hash, block_number, anchored_timestamp = await asyncio.to_thread(
                blockchain.recover_confirmed_transaction, tx_hash_value
            )
            anchor_record["transaction_hash"] = tx_hash
            anchor_record["block_number"] = block_number
            anchor_record["anchored_at"] = datetime.fromtimestamp(anchored_timestamp, timezone.utc).isoformat()
        except Exception as exc:
            logger.warning(
                "Could not enrich recovered passport root anchor metadata for passport_id=%s "
                "using transaction log lookup; persisting verified on-chain anchor data only: %s",
                passport_id, exc, exc_info=True,
            )

        self._create_anchor(passport_id, anchor_record)
        self._audit(
            "passport_root_anchor_recovered",
            passport_id,
            audit_context,
            summary=f"Passport root anchor recovered from chain for {passport_id} (no new transaction submitted)",
            extra_metadata={
                "transaction_hash": anchor_record.get("transaction_hash"),
                "block_number": anchor_record.get("block_number"),
            },
        )
        return anchor_record

    def _build_anchor_record(
        self,
        *,
        passport_id: str,
        passport_hash: str,
        passport_key: str,
        transaction_hash: Optional[str],
        block_number: Optional[int],
        anchored_timestamp: Any,
        contract_address: str,
    ) -> Dict[str, Any]:
        anchored_at = (
            anchored_timestamp
            if isinstance(anchored_timestamp, str)
            else datetime.fromtimestamp(anchored_timestamp, timezone.utc).isoformat()
        )
        return {
            "passport_id": passport_id,
            "passport_hash": passport_hash,
            "passport_key": passport_key,
            "transaction_hash": transaction_hash,
            "block_number": block_number,
            "anchored_at": anchored_at,
            "blockchain_network": BLOCKCHAIN_NETWORK,
            "contract_address": contract_address,
            "chain_id": 11155111,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "hash_algorithm": HASH_ALGORITHM,
            "anchoring_method": ANCHORING_METHOD,
        }

    def _create_anchor(self, passport_id: str, anchor_record: Dict[str, Any]) -> None:
        """Persist anchor metadata without allowing replacement or deletion."""
        existing = self.repository.get(passport_id)
        if existing:
            if existing.get("passport_hash", "").lower() != anchor_record["passport_hash"].lower():
                raise PassportRootConflictError(
                    f"Passport {passport_id} already has a different anchored root"
                )
            return
        self.repository.set(passport_id, anchor_record)

    # ------------------------------------------------------------------
    # Verification (extends POST /passports/{id}/verify)
    # ------------------------------------------------------------------

    async def verify_passport_root_status(
        self,
        passport_id: str,
        integrity: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return the local integrity result plus a blockchain anchor_status.

        ``integrity`` is caller-computed (see the matching docstring note on
        anchor_passport_root above) -- always
        ``domains.passport.integrity.verify_passport_integrity``'s own
        output, never recomputed a second way here.

        Local integrity ALWAYS runs first and is never overridden by chain
        state: a blockchain root is never allowed to convert a FAIL or
        UNVERIFIABLE local result into PASS (see
        docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md section 16). anchor_status
        is one of PASS, FAIL, UNVERIFIABLE, NOT_ANCHORED, NETWORK_ERROR,
        CHAIN_MISMATCH, or INVALID_PROOF.
        """
        eligible, reasons = passport_root_eligibility(integrity)
        passport_key = compute_passport_key(passport_id)

        result: Dict[str, Any] = {
            **integrity,
            "passport_id": passport_id,
            "passport_key": passport_key,
            "blockchain_network": None,
            "contract_address": None,
            "chain_id": None,
            "transaction_hash": None,
            "block_number": None,
            "on_chain_root": None,
            "anchor_ineligible_reasons": reasons,
        }

        if not eligible:
            any_fail = any(integrity.get(field) == FAIL for field in _REQUIRED_INTEGRITY_FIELDS)
            result["anchor_status"] = FAIL if any_fail else UNVERIFIABLE
            return result

        passport_hash = integrity["recomputed_passport_hash"]

        try:
            blockchain = self._ensure_blockchain()
        except Exception as exc:
            result["anchor_status"] = "NETWORK_ERROR"
            result["anchor_error"] = sanitize_analysis_error(exc)
            return result

        try:
            on_chain = await asyncio.to_thread(blockchain.get_passport_root, bytes.fromhex(passport_key))
        except ConnectionError as exc:
            result["anchor_status"] = "NETWORK_ERROR"
            result["anchor_error"] = sanitize_analysis_error(exc)
            return result
        except ValueError as exc:
            result["anchor_status"] = "CHAIN_MISMATCH" if "Wrong network" in str(exc) else "NETWORK_ERROR"
            result["anchor_error"] = sanitize_analysis_error(exc)
            return result
        except Exception as exc:  # noqa: BLE001 - surfaced as a non-fatal verify state
            result["anchor_status"] = "NETWORK_ERROR"
            result["anchor_error"] = sanitize_analysis_error(exc)
            return result

        result["blockchain_network"] = BLOCKCHAIN_NETWORK
        result["contract_address"] = blockchain.contract_address
        result["chain_id"] = blockchain.chain_id

        if on_chain is None:
            result["anchor_status"] = "NOT_ANCHORED"
            return result

        on_chain_root = on_chain.get("passport_root", "").lower().removeprefix("0x")
        result["on_chain_root"] = on_chain_root

        if self.repository:
            persisted = self.repository.get(passport_id)
            if persisted:
                result["transaction_hash"] = persisted.get("transaction_hash")
                result["block_number"] = persisted.get("block_number")

        if on_chain_root != passport_hash.lower():
            result["anchor_status"] = "INVALID_PROOF"
            return result

        result["anchor_status"] = PASS
        return result

    # ------------------------------------------------------------------
    # Public, existence-only verification (no confidential snapshot needed)
    # ------------------------------------------------------------------

    async def public_root_existence(self, passport_id: str, passport_hash: str) -> Dict[str, Any]:
        """Confirm/deny that a passport root exists on the expected registry.

        This is intentionally the ONLY passport-root check safe to expose
        without authentication: it takes a passport_id and a claimed
        passport_hash (both effectively public once a passport has been
        shared) and answers only "does this exact root exist on the expected
        LexProofPassportRegistry", never anything derived from the
        confidential verification_snapshot. On-chain existence is a strictly
        weaker claim than full passport integrity and must never be labeled
        as such.
        """
        passport_key = compute_passport_key(passport_id)
        try:
            root_bytes = passport_root_bytes32(passport_hash)
        except ValueError as exc:
            return {
                "passport_id": passport_id,
                "passport_key": passport_key,
                "exists": False,
                "status": "INVALID_INPUT",
                "error": str(exc),
            }

        try:
            blockchain = self._ensure_blockchain()
        except Exception as exc:
            return {
                "passport_id": passport_id,
                "passport_key": passport_key,
                "exists": False,
                "status": "NETWORK_ERROR",
                "error": sanitize_analysis_error(exc),
            }

        try:
            matches = await asyncio.to_thread(
                blockchain.verify_passport_root, bytes.fromhex(passport_key), root_bytes
            )
        except Exception as exc:
            return {
                "passport_id": passport_id,
                "passport_key": passport_key,
                "exists": False,
                "status": "NETWORK_ERROR",
                "error": sanitize_analysis_error(exc),
            }

        return {
            "passport_id": passport_id,
            "passport_key": passport_key,
            "exists": matches,
            "status": "ANCHORED" if matches else "NOT_ANCHORED",
            "blockchain_network": BLOCKCHAIN_NETWORK,
            "contract_address": blockchain.contract_address,
            "chain_id": blockchain.chain_id,
        }

    def _audit(
        self,
        action: str,
        passport_id: str,
        audit_context: Dict[str, Any],
        *,
        summary: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = {**audit_context["metadata_base"], **(extra_metadata or {})}
        record_audit_event(
            actor_id=audit_context["actor_id"],
            action=action,
            resource_type="passport_anchor",
            resource_id=passport_id,
            summary=summary,
            contract_id=audit_context.get("contract_id"),
            org_id=audit_context.get("org_id"),
            metadata=metadata,
        )

    @staticmethod
    def _validate_passport_id(passport_id: str) -> None:
        if not isinstance(passport_id, str) or not passport_id.strip() or len(passport_id) > 256:
            raise ValueError("passport_id must be between 1 and 256 characters")


# Global instance (lazy loaded), mirroring get_ethereum_anchor_service.
_passport_root_anchor_service: Optional[PassportRootAnchorService] = None


def get_passport_root_anchor_service(
    settings: Optional[LexProofSettings] = None,
    repository: Optional[FirestoreRepository] = None,
) -> PassportRootAnchorService:
    global _passport_root_anchor_service

    if _passport_root_anchor_service is None:
        _passport_root_anchor_service = PassportRootAnchorService(
            settings=settings,
            repository=repository,
        )
    elif repository is not None:
        _passport_root_anchor_service.repository = repository

    return _passport_root_anchor_service
