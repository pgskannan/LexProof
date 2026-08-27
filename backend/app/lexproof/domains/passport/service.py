"""PassportService — creates immutable legal intelligence passports.

This service orchestrates the creation of ContractPassports by leveraging
the existing ContractRiskEdge AI analysis engine. It ensures deterministic
hashing of all passport components and maintains audit trails.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import (
    ContractPassport,
    ContractPassportCreate,
    ContractPassportResponse,
    ContractPassportSummary,
    PassportStatus,
)
from .utils.hashing import (
    hash_ai_analysis,
    hash_evidence_package,
    hash_document,
    hash_original_document,
    hash_normalized_document,
    hash_policy_version,
    compute_passport_hash,
    generate_passport_id,
    generate_evidence_id,
)
from .validation import validate_passport_creation_analysis
from .utils.evidence import count_legal_evidence_findings
from typing import Awaitable, Callable
from ...repositories.firestore import FirestoreRepository

logger = logging.getLogger(__name__)

AnalysisEngine = Callable[[str, str], Awaitable[Dict[str, Any]]]
_passports: Dict[str, ContractPassport] = {}
_passports_by_contract: Dict[tuple[str, int], str] = {}
_evidence_by_passport: Dict[str, List[Dict[str, Any]]] = {}


def _is_visible_to_tenant(record: Dict[str, Any], tenant_id: str) -> bool:
    """Support legacy ownerless passports while preserving tenant isolation."""
    owner_id = record.get("owner_id")
    return not owner_id or owner_id == tenant_id


class PassportService:
    """Service for creating and managing legal passports."""

    def __init__(
        self,
        analysis_engine: AnalysisEngine,
        user_id: str,
        tenant_id: str,
        audit_sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        repository: Optional[FirestoreRepository] = None,
    ):
        """Initialize PassportService.

        Args:
            ai_repo: AI repository for triggering analysis
            vector_repo: Vector repository (for future use)
            ingest_repo: Ingestion repository (for future use)
            event_bus: Event bus for audit events
            user: Current user context
            tenant_id: Tenant identifier
            audit_trail: Audit trail service
        """
        self.analysis_engine = analysis_engine
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.audit_sink = audit_sink
        self.repository = repository

    async def create_passport(
        self,
        contract_id: str,
        contract_version: int,
        policy_version: str,
        document_content: str,
        policy_content: Optional[str] = None,
        normalized_document: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContractPassportResponse:
        """Create a new contract passport.

        This method:
        1. Triggers AI analysis using existing ContractRiskEdge engine
        2. Computes deterministic hashes for all components
        3. Creates evidence items from analysis results
        4. Creates immutable passport snapshot

        Args:
            contract_id: Contract identifier
            contract_version: Contract version number
            policy_version: Policy version identifier
            document_content: Original document content
            policy_content: Optional policy content
            metadata: Additional metadata

        Returns:
            Created contract passport

        Raises:
            ValueError: If contract analysis fails
        """
        logger.info(f"Creating passport for contract {contract_id}, version {contract_version}")

        try:
            # Step 1: Trigger AI analysis using existing ContractRiskEdge engine
            analysis_result = await self.analysis_engine(document_content, policy_content or "")
            if not isinstance(analysis_result, dict):
                raise ValueError("ContractRiskEdge analysis engine returned an invalid result")

            # Step 1.5: Validate AI analysis response structure and completeness
            validate_passport_creation_analysis(analysis_result)

            # Step 2: Compute hashes for all components
            document_hash = hash_document(document_content, normalized_document)
            policy_hash = hash_policy_version(
                policy_id="default-policy",
                policy_content=policy_content,
                version=policy_version,
            )
            analysis_hash = hash_ai_analysis(
                analysis_result=analysis_result,
                analysis_type="risk_and_compliance",
            )

            # Step 3: Create evidence items from analysis results
            passport_id = generate_passport_id()
            evidence_items = await self._create_evidence_items(
                passport_id=passport_id,
                contract_id=contract_id,
                contract_version=contract_version,
                analysis_result=analysis_result,
            )
            evidence_hash = hash_evidence_package(evidence_items)

            # Step 4: Compute final passport hash
            passport_hash = compute_passport_hash(
                document_hash=document_hash,
                policy_hash=policy_hash,
                analysis_hash=analysis_hash,
                evidence_hash=evidence_hash,
            )

            # Step 5: Create passport
            passport = ContractPassport(
                passport_id=passport_id,
                contract_id=contract_id,
                contract_version=contract_version,
                document_hash=document_hash,
                policy_hash=policy_hash,
                analysis_hash=analysis_hash,
                evidence_hash=evidence_hash,
                risk_score=float(analysis_result.get('risk_score', 0.0)),
                compliance_score=float(analysis_result.get('compliance_score', 0.0)),
                policy_version=policy_version,
            evidence_count=count_legal_evidence_findings(evidence_items),
            created_at=datetime.utcnow(),
            created_by=self.user_id,
            status=PassportStatus.CREATED,
            audit_events=[],
            metadata={
                **(metadata or {}),
                "passport_hash": passport_hash,
                "original_document_hash": hash_original_document(document_content),
                "normalized_document_hash": hash_normalized_document(normalized_document),
                "verification_snapshot": {
                    "document_content": document_content,
                    "normalized_document": normalized_document,
                    "policy_content": policy_content or "",
                    "policy_id": "default-policy",
                    "policy_version": policy_version,
                    "analysis_result": analysis_result,
                    "analysis_type": "risk_and_compliance",
                },
            },
            )

            # Step 6: Record audit events
            _passports[passport.passport_id] = passport
            _passports_by_contract[(contract_id, contract_version)] = passport.passport_id
            _evidence_by_passport[passport.passport_id] = evidence_items
            if self.repository:
                self.repository.set(
                    passport.passport_id,
                    {**passport.model_dump(mode="json"), "id": passport.passport_id, "owner_id": self.user_id},
                )
            await self._record_audit_events(
                passport=passport,
                evidence_items=evidence_items,
            )

            logger.info(f"Successfully created passport {passport.passport_id} for contract {contract_id}")

            return ContractPassportResponse.model_validate(passport)

        except Exception as e:
            logger.error(f"Failed to create passport for contract {contract_id}: {e}")
            raise ValueError(f"Passport creation failed: {str(e)}") from e

    async def _create_evidence_items(
        self,
        passport_id: str,
        contract_id: str,
        contract_version: int,
        analysis_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Create evidence items from analysis results.

        Args:
            contract_id: Contract identifier
            contract_version: Contract version number
            analysis_result: AI analysis result dictionary

        Returns:
            List of evidence item dictionaries
        """
        evidence_items = []

        # Extract findings from analysis result
        findings = analysis_result.get('findings', [])
        # NOTE: risk_score and compliance_score are extracted directly without default
        # because they have been validated to be present in validate_passport_creation_analysis()
        risk_score = analysis_result['risk_score']
        compliance_score = analysis_result['compliance_score']
        evidence_created_at = datetime.utcnow().isoformat()

        # Create evidence items for each finding
        for i, finding in enumerate(findings, 1):
            evidence_item = {
                "evidence_id": generate_evidence_id(),
                "passport_id": passport_id,
                "evidence_type": "clause",
                "title": f"Risk Finding {i}: {finding.get('title', 'Unknown')}",
                "description": finding.get('description', ''),
                "content": json.dumps(finding, sort_keys=True),
                "content_type": "application/json",
                "risk_impact": finding.get('risk_impact'),  # Keep as-is (already validated)
                "compliance_impact": finding.get('compliance_impact'),  # Keep as-is (already validated)
                "evidence_status": "valid",
                "contract_reference": finding.get('source_section', ''),
                "policy_reference": finding.get('policy_reference', ''),
                "analysis_reference": finding.get('id', ''),
                "source": "ai_analysis",
                "source_id": f"finding_{i}",
                "hash": None,  # Will be computed
                "metadata": {
                    "finding_severity": finding.get('severity', 'medium'),
                    "risk_category": finding.get('category', 'general'),
                    "evidence_quote": finding.get('evidence_quote', ''),
                    "source_section": finding.get('source_section', ''),
                    "recommendation": finding.get('recommendation', ''),
                },
                "owner_id": self.user_id,
                "contract_id": contract_id,
                "contract_version": contract_version,
                "created_at": evidence_created_at,
            }

            # Compute hash for evidence item
            evidence_item["hash"] = self._compute_evidence_item_hash(evidence_item)

            evidence_items.append(evidence_item)

        # Add evidence for overall scores
        score_evidence = {
            "evidence_id": generate_evidence_id(),
            "passport_id": passport_id,
            "evidence_type": "metadata",
            "title": "Risk and Compliance Scores",
            "description": "Overall risk and compliance assessment",
            "content": json.dumps({
                "risk_score": risk_score,
                "compliance_score": compliance_score,
            }, indent=2),
            "content_type": "application/json",
            "risk_impact": None,
            "compliance_impact": None,
            "evidence_status": "valid",
            "contract_reference": None,
            "policy_reference": None,
            "analysis_reference": None,
            "source": "ai_analysis",
            "source_id": "overall_scores",
            "hash": None,
            "metadata": {
                "assessment_type": "overall",
            },
            "owner_id": self.user_id,
            "contract_id": contract_id,
            "contract_version": contract_version,
            "created_at": evidence_created_at,
        }

        score_evidence["hash"] = self._compute_evidence_item_hash(score_evidence)
        evidence_items.append(score_evidence)

        return evidence_items

    def _compute_evidence_item_hash(self, evidence_item: Dict[str, Any]) -> str:
        """Compute hash for evidence item.

        Args:
            evidence_item: Evidence item dictionary

        Returns:
            SHA-256 hash
        """
        from .utils.hashing import hash_evidence_item

        return hash_evidence_item(evidence_item)

    async def _record_audit_events(
        self,
        passport: ContractPassport,
        evidence_items: List[Dict[str, Any]],
    ) -> None:
        """Record audit events for passport creation.

        Args:
            passport: Created passport
            evidence_items: List of evidence items
        """
        try:
            # Record passport creation event
            audit_event = {
                "event_type": "passport_created",
                "passport_id": passport.passport_id,
                "contract_id": passport.contract_id,
                "contract_version": passport.contract_version,
                "timestamp": passport.created_at.isoformat(),
                "created_by": passport.created_by,
                "risk_score": passport.risk_score,
                "compliance_score": passport.compliance_score,
                "policy_version": passport.policy_version,
                "evidence_count": passport.evidence_count,
            }

            # Add to audit events
            object.__setattr__(passport, "audit_events", [audit_event])
            if self.audit_sink:
                await self.audit_sink(audit_event)

            # Log audit event
            logger.info(f"Recorded audit event: {audit_event['event_type']} for passport {passport.passport_id}")

        except Exception as e:
            logger.error(f"Failed to record audit event: {e}")

    async def get_passport(self, passport_id: str) -> Optional[ContractPassportResponse]:
        """Retrieve a passport by ID.

        Args:
            passport_id: Passport identifier

        Returns:
            Passport if found, None otherwise
        """
        passport = _passports.get(passport_id)
        if passport is None and self.repository:
            stored = self.repository.get(passport_id)
            if stored and _is_visible_to_tenant(stored, self.tenant_id):
                passport = ContractPassport.model_validate(stored)
        return ContractPassportResponse.model_validate(passport) if passport else None

    async def get_passport_by_contract(
        self,
        contract_id: str,
        contract_version: int,
    ) -> Optional[ContractPassportResponse]:
        """Retrieve a passport by contract and version.

        Args:
            contract_id: Contract identifier
            contract_version: Contract version number

        Returns:
            Passport if found, None otherwise
        """
        passport_id = _passports_by_contract.get((contract_id, contract_version))
        if passport_id:
            return await self.get_passport(passport_id)
        if self.repository:
            for stored in self.repository.stream():
                if stored.get("contract_id") == contract_id and stored.get("contract_version") == contract_version:
                    if not _is_visible_to_tenant(stored, self.tenant_id):
                        continue
                    return ContractPassportResponse.model_validate(stored)
        return None

    async def list_passports(
        self,
        contract_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ContractPassportSummary]:
        """List passports with optional filtering.

        Args:
            contract_id: Optional contract ID filter
            limit: Maximum number of passports to return
            offset: Pagination offset

        Returns:
            List of passport summaries
        """
        values = list(_passports.values())
        if contract_id:
            values = [item for item in values if item.contract_id == contract_id]
        values = values[offset:offset + limit]
        return [ContractPassportSummary.model_validate(item) for item in values]

    async def get_evidence(self, passport_id: str) -> List[Dict[str, Any]]:
        """Return the evidence captured in a passport snapshot."""
        return list(_evidence_by_passport.get(passport_id, []))
