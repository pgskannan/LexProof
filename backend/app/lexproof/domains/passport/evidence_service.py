"""EvidenceService — manages evidence items in legal passports.

This service handles the creation, retrieval, and management of evidence items
that support contract intelligence assessments in ContractPassports.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import (
    EvidenceItem,
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceItemSummary,
    EvidenceItemUpdate,
    EvidenceStatus,
    EvidenceType,
)
from .utils.evidence import count_legal_evidence_findings, filter_legal_evidence_findings
from .utils.hashing import (
    hash_evidence_item,
    generate_evidence_id,
)
from ...repositories.firestore import FirestoreRepository

logger = logging.getLogger(__name__)


class EvidenceService:
    """Service for managing evidence items."""

    def __init__(self, repository: Optional[FirestoreRepository] = None, owner_id: Optional[str] = None, passport_repository: Optional[FirestoreRepository] = None, anchor_repository: Optional[FirestoreRepository] = None):
        """Initialize EvidenceService."""
        self.evidence_items: Dict[str, EvidenceItem] = {}
        self.repository = repository
        self.owner_id = owner_id
        self.passport_repository = passport_repository
        self.anchor_repository = anchor_repository

    def is_evidence_anchored(self, evidence_id: str) -> bool:
        """Return whether a confirmed anchor exists for the evidence ID."""
        if self.anchor_repository:
            return bool(self.anchor_repository.get(evidence_id))
        if self.repository and hasattr(self.repository, "is_evidence_anchored"):
            return bool(self.repository.is_evidence_anchored(evidence_id))
        return False

    def _ensure_evidence_is_mutable(self, evidence_id: str) -> None:
        if self.is_evidence_anchored(evidence_id):
            raise ValueError(f"Anchored evidence cannot be modified: {evidence_id}")

    def passport_exists(self, passport_id: str) -> bool:
        if self.passport_repository is None:
            return True
        record = self.passport_repository.get(passport_id)
        return bool(record and (not self.owner_id or not record.get("owner_id") or record.get("owner_id") == self.owner_id))

    async def create_evidence_item(
        self,
        passport_id: str,
        evidence_data: EvidenceItemCreate,
        user: Any,
    ) -> EvidenceItemResponse:
        """Create a new evidence item.

        Args:
            passport_id: Parent passport identifier
            evidence_data: Evidence item creation data
            user: Current user context

        Returns:
            Created evidence item

        Raises:
            ValueError: If evidence item creation fails
        """
        logger.info(f"Creating evidence item {evidence_data.title} for passport {passport_id}")

        try:
            # Create evidence item
            evidence_item = EvidenceItem(
                evidence_id=generate_evidence_id(),
                passport_id=passport_id,
                evidence_type=evidence_data.evidence_type,
                title=evidence_data.title,
                description=evidence_data.description,
                content=evidence_data.content,
                content_type=evidence_data.content_type,
                risk_impact=evidence_data.risk_impact,
                compliance_impact=evidence_data.compliance_impact,
                evidence_status=evidence_data.evidence_status,
                contract_reference=evidence_data.contract_reference,
                policy_reference=evidence_data.policy_reference,
                analysis_reference=evidence_data.analysis_reference,
                created_at=datetime.utcnow(),
                verified_at=None,
                source=evidence_data.source,
                source_id=evidence_data.source_id,
                hash=None,  # Will be computed
                metadata=evidence_data.metadata,
            )

            # Compute hash
            evidence_item.hash = hash_evidence_item(evidence_item.dict())

            # Store in memory (in production, this would be a database)
            self.evidence_items[evidence_item.evidence_id] = evidence_item
            if self.repository:
                self.repository.set(
                    evidence_item.evidence_id,
                    {**evidence_item.model_dump(mode="json"), "id": evidence_item.evidence_id, "owner_id": self.owner_id},
                )

            logger.info(f"Successfully created evidence item {evidence_item.evidence_id}")

            return EvidenceItemResponse.model_validate(evidence_item)

        except Exception as e:
            logger.error(f"Failed to create evidence item: {e}")
            raise ValueError(f"Evidence item creation failed: {str(e)}") from e

    async def get_evidence_item(self, evidence_id: str) -> Optional[EvidenceItemResponse]:
        """Retrieve an evidence item by ID.

        Args:
            evidence_id: Evidence item identifier

        Returns:
            Evidence item if found, None otherwise
        """
        evidence_item = self.evidence_items.get(evidence_id)

        if not evidence_item and self.repository:
            record = self.repository.get(evidence_id)
            if record:
                evidence_item = EvidenceItem.model_validate(record)
                self.evidence_items[evidence_id] = evidence_item

        if evidence_item:
            return EvidenceItemResponse.model_validate(evidence_item)

        logger.warning(f"Evidence item not found: {evidence_id}")
        return None

    async def get_evidence_by_passport(
        self,
        passport_id: str,
    ) -> List[EvidenceItemSummary]:
        """Retrieve all evidence items for a passport.

        Args:
            passport_id: Parent passport identifier

        Returns:
            List of evidence item summaries
        """
        # Filter evidence items by passport_id (in production, this would be a database query)
        evidence_summaries = []

        for evidence_item in self.evidence_items.values():
            if evidence_item.passport_id == passport_id:
                evidence_summaries.append(EvidenceItemSummary.model_validate(evidence_item))

        if self.repository:
            for record in self.repository.stream():
                if record.get("passport_id") != passport_id:
                    continue
                if self.owner_id and record.get("owner_id") and record.get("owner_id") != self.owner_id:
                    continue
                if not record.get("created_at") and self.passport_repository:
                    passport = self.passport_repository.get(passport_id)
                    if passport and passport.get("created_at"):
                        record = {**record, "created_at": passport["created_at"]}
                        evidence_id = record.get("id") or record.get("evidence_id")
                        if not self.is_evidence_anchored(evidence_id):
                            self.repository.set(evidence_id, {"created_at": record["created_at"]}, merge=True)
                evidence_summaries.append(EvidenceItemSummary.model_validate(record))

        # Sort by created_at (newest first)
        evidence_summaries.sort(
            key=lambda x: x.created_at,
            reverse=True
        )

        return evidence_summaries

    async def update_evidence_item(
        self,
        evidence_id: str,
        update_data: EvidenceItemUpdate,
    ) -> Optional[EvidenceItemResponse]:
        """Update an evidence item.

        Args:
            evidence_id: Evidence item identifier
            update_data: Update data

        Returns:
            Updated evidence item if found, None otherwise
        """
        evidence_item = self.evidence_items.get(evidence_id)

        if not evidence_item and self.repository:
            record = self.repository.get(evidence_id)
            if record:
                evidence_item = EvidenceItem.model_validate(record)
                self.evidence_items[evidence_id] = evidence_item

        if not evidence_item:
            logger.warning(f"Evidence item not found: {evidence_id}")
            return None

        try:
            self._ensure_evidence_is_mutable(evidence_id)
            # Update status and verification timestamp
            if update_data.evidence_status:
                evidence_item.evidence_status = update_data.evidence_status

            if update_data.verified_at:
                evidence_item.verified_at = update_data.verified_at

            # Recompute hash (content may have changed)
            evidence_item.hash = hash_evidence_item(evidence_item.dict())
            if self.repository:
                self.repository.set(
                    evidence_id,
                    {**evidence_item.model_dump(mode="json"), "id": evidence_id, "owner_id": self.owner_id},
                )

            logger.info(f"Successfully updated evidence item {evidence_id}")

            return EvidenceItemResponse.model_validate(evidence_item)

        except Exception as e:
            logger.error(f"Failed to update evidence item: {e}")
            raise ValueError(f"Evidence item update failed: {str(e)}") from e

    async def delete_evidence_item(self, evidence_id: str) -> bool:
        """Delete an evidence item.

        Args:
            evidence_id: Evidence item identifier

        Returns:
            True if deleted, False if not found
        """
        if evidence_id in self.evidence_items:
            self._ensure_evidence_is_mutable(evidence_id)
            del self.evidence_items[evidence_id]
            if self.repository:
                self.repository.delete(evidence_id)
            logger.info(f"Successfully deleted evidence item {evidence_id}")
            return True

        if self.repository and self.repository.get(evidence_id):
            self._ensure_evidence_is_mutable(evidence_id)
            self.repository.delete(evidence_id)
            logger.info(f"Successfully deleted evidence item {evidence_id}")
            return True

        logger.warning(f"Evidence item not found: {evidence_id}")
        return False

    async def verify_evidence_item(
        self,
        evidence_id: str,
        verification_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[EvidenceItemResponse]:
        """Verify an evidence item.

        Args:
            evidence_id: Evidence item identifier
            verification_data: Optional verification data

        Returns:
            Verified evidence item if found, None otherwise
        """
        evidence_item = self.evidence_items.get(evidence_id)

        if not evidence_item and self.repository:
            record = self.repository.get(evidence_id)
            if record:
                evidence_item = EvidenceItem.model_validate(record)
                self.evidence_items[evidence_id] = evidence_item

        if not evidence_item:
            logger.warning(f"Evidence item not found: {evidence_id}")
            return None

        try:
            self._ensure_evidence_is_mutable(evidence_id)
            # Update verification timestamp
            evidence_item.verified_at = datetime.utcnow()

            # Add verification data to metadata if provided
            if verification_data:
                if not evidence_item.metadata:
                    evidence_item.metadata = {}
                evidence_item.metadata["verified_at"] = evidence_item.verified_at.isoformat()
                evidence_item.metadata["verification_data"] = verification_data

            # Recompute hash
            evidence_item.hash = hash_evidence_item(evidence_item.dict())
            if self.repository:
                self.repository.set(
                    evidence_id,
                    {**evidence_item.model_dump(mode="json"), "id": evidence_id, "owner_id": self.owner_id},
                )

            logger.info(f"Successfully verified evidence item {evidence_id}")

            return EvidenceItemResponse.model_validate(evidence_item)

        except Exception as e:
            logger.error(f"Failed to verify evidence item: {e}")
            raise ValueError(f"Evidence item verification failed: {str(e)}") from e

    async def batch_create_evidence(
        self,
        passport_id: str,
        evidence_items: List[Dict[str, Any]],
        user: Any,
    ) -> List[EvidenceItemResponse]:
        """Create multiple evidence items at once.

        Args:
            passport_id: Parent passport identifier
            evidence_items: List of evidence item dictionaries
            user: Current user context

        Returns:
            List of created evidence items
        """
        created_items = []

        for evidence_data in evidence_items:
            try:
                # Create evidence item from dictionary
                evidence_create = EvidenceItemCreate(**evidence_data)
                evidence_item = await self.create_evidence_item(
                    passport_id=passport_id,
                    evidence_data=evidence_create,
                    user=user,
                )
                created_items.append(evidence_item)

            except Exception as e:
                logger.error(f"Failed to create evidence item: {e}")
                continue

        logger.info(f"Batch created {len(created_items)} evidence items for passport {passport_id}")

        return created_items

    async def get_evidence_statistics(
        self,
        passport_id: str,
    ) -> Dict[str, Any]:
        """Get statistics for evidence items in a passport.

        Args:
            passport_id: Parent passport identifier

        Returns:
            Dictionary with evidence statistics
        """
        evidence_items = await self.get_evidence_by_passport(passport_id)

        # Count by type
        type_counts = {}
        for item in evidence_items:
            evidence_type = item.evidence_type.value if hasattr(item.evidence_type, 'value') else str(item.evidence_type)
            type_counts[evidence_type] = type_counts.get(evidence_type, 0) + 1

        # Count by status
        status_counts = {}
        for item in evidence_items:
            evidence_status = item.evidence_status.value if hasattr(item.evidence_status, 'value') else str(item.evidence_status)
            status_counts[evidence_status] = status_counts.get(evidence_status, 0) + 1

        # Calculate average risk and compliance impacts
        risk_impacts = [item.risk_impact for item in evidence_items if item.risk_impact is not None]
        compliance_impacts = [item.compliance_impact for item in evidence_items if item.compliance_impact is not None]

        avg_risk_impact = sum(risk_impacts) / len(risk_impacts) if risk_impacts else 0.0
        avg_compliance_impact = sum(compliance_impacts) / len(compliance_impacts) if compliance_impacts else 0.0

        legal_evidence = filter_legal_evidence_findings(evidence_items)

        return {
            "total_count": count_legal_evidence_findings(evidence_items),
            "legal_findings_count": len(legal_evidence),
            "type_counts": type_counts,
            "status_counts": status_counts,
            "avg_risk_impact": avg_risk_impact,
            "avg_compliance_impact": avg_compliance_impact,
        }
