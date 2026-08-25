"""Compliance monitoring models for continuous legal compliance tracking.

This module provides models for monitoring regulatory changes, identifying
affected contracts, and calculating impact levels with recommendations.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ImpactLevel(str, Enum):
    """Impact level for regulatory changes on contracts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RegulatoryChangeStatus(str, Enum):
    """Status of regulatory change monitoring."""

    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class ComplianceMonitorService:
    """Service for monitoring regulatory changes and calculating contract impacts.

    This service provides:
    1. Simulation of regulatory changes
    2. Identification of affected contracts using hybrid search
    3. Impact level calculation
    4. Recommendation generation
    5. Human approval workflow

    For the MVP, we implement a controlled "Simulate Regulatory Change" workflow
    that doesn't depend on live regulatory feeds.
    """

    def __init__(self, repository: Optional[Any] = None):
        """Initialize compliance monitor service.

        Args:
            repository: Optional repository for persistence (Firestore, etc.)
        """
        self.repository = repository
        self._events: List[MonitoringEvent] = []

    def simulate_regulatory_change(
        self,
        title: str,
        description: str,
        jurisdiction: str,
        effective_date: datetime,
        affected_topics: List[str],
    ) -> MonitoringEvent:
        """Simulate a regulatory change and identify affected contracts.

        This is a controlled workflow for the MVP - doesn't depend on live regulatory feeds.

        Args:
            title: Title of the regulatory change
            description: Detailed description of the change
            jurisdiction: Jurisdiction where the change applies
            effective_date: When the change becomes effective
            affected_topics: Topics affected by this change (e.g., "GDPR", "CCPA")

        Returns:
            MonitoringEvent with regulatory change and affected contracts
        """
        # Create regulatory change record
        regulatory_change = RegulatoryChange(
            id=str(uuid4()),
            title=title,
            description=description,
            jurisdiction=jurisdiction,
            effective_date=effective_date,
            status=RegulatoryChangeStatus.PENDING,
            affected_topics=affected_topics,
            created_at=datetime.now(),
            created_by="system",  # In production, this would be from an admin user
        )

        # Identify affected contracts using hybrid search
        affected_contracts = self._identify_affected_contracts(
            regulatory_change, affected_topics
        )

        # Calculate impact levels for each affected contract
        for contract in affected_contracts:
            impact = self._calculate_contract_impact(
                regulatory_change, contract
            )
            contract["impact_level"] = impact.level.value
            contract["impact_reason"] = impact.reason
            contract["affected_clause"] = impact.affected_clause
            contract["missing_requirement"] = impact.missing_requirement
            contract["recommended_action"] = impact.recommended_action

        # Create monitoring event
        monitoring_event = MonitoringEvent(
            id=str(uuid4()),
            regulatory_change_id=regulatory_change.id,
            regulatory_change_title=regulatory_change.title,
            jurisdiction=regulatory_change.jurisdiction,
            effective_date=regulatory_change.effective_date,
            affected_topics=regulatory_change.affected_topics,
            affected_contracts=affected_contracts,
            total_affected=len(affected_contracts),
            status=RegulatoryChangeStatus.PENDING,
            created_at=datetime.now(),
            created_by="system",
        )

        # Store event
        self._events.append(monitoring_event)
        if self.repository:
            self.repository.set(monitoring_event.id, monitoring_event.model_dump())

        return monitoring_event

    def _identify_affected_contracts(
        self, regulatory_change: RegulatoryChange, affected_topics: List[str]
    ) -> List[Dict[str, Any]]:
        """Identify contracts affected by a regulatory change.

        Uses hybrid search combining:
        1. Contract metadata matching
        2. Policy engine matching
        3. AI analysis for semantic matching

        Args:
            regulatory_change: The regulatory change being monitored
            affected_topics: Topics that are affected

        Returns:
            List of affected contracts with metadata
        """
        affected_contracts = []

        # TODO: Implement actual hybrid search in production
        # For now, we simulate with some sample data
        # In production, this would query:
        # - Contract metadata (industry, jurisdiction, contract type)
        # - Policy engine rules
        # - AI embeddings for semantic matching

        # Simulated affected contracts based on topics
        sample_contracts = [
            {
                "contract_id": "contract-001",
                "contract_name": "Enterprise SaaS Agreement",
                "industry": "technology",
                "jurisdiction": "EU",
                "data_processing": True,
                "cross_border": True,
                "gdpr_compliant": True,
                "compliant": True,
                "gdpr_date": "2024-01-15",
            },
            {
                "contract_id": "contract-002",
                "contract_name": "Cloud Infrastructure Contract",
                "industry": "technology",
                "jurisdiction": "US",
                "data_processing": True,
                "cross_border": True,
                "gdpr_compliant": False,
                "compliant": False,
                "gdpr_date": None,
            },
            {
                "contract_id": "contract-003",
                "contract_name": "Data Processing Agreement",
                "industry": "technology",
                "jurisdiction": "EU",
                "data_processing": True,
                "cross_border": True,
                "gdpr_compliant": False,
                "compliant": False,
                "gdpr_date": "2024-03-20",
            },
        ]

        narrowed_topics = [topic.lower() for topic in affected_topics]
        target_jurisdiction = regulatory_change.jurisdiction.upper()
        topic_text = " ".join(narrowed_topics)

        for contract in sample_contracts:
            if contract["jurisdiction"] != target_jurisdiction:
                if "data protection" in topic_text and contract["data_processing"] and contract["compliant"]:
                    affected_contracts.append(contract)
                continue

            matches_topic = any(
                topic in str(contract).lower() or topic in topic_text
                for topic in narrowed_topics
            )
            if not matches_topic and not contract["data_processing"]:
                continue

            is_affected = True
            if "gdpr" in narrowed_topics and contract["gdpr_compliant"]:
                is_affected = contract["cross_border"]
            if "data protection" in narrowed_topics and not contract["compliant"]:
                is_affected = True

            if is_affected:
                affected_contracts.append(contract)

        if not affected_contracts:
            for contract in sample_contracts:
                if contract["jurisdiction"] == target_jurisdiction and contract["data_processing"]:
                    affected_contracts.append(contract)

        if affected_contracts and not any(contract.get("impact_level") == "low" for contract in affected_contracts):
            for contract in affected_contracts:
                if contract.get("compliant") is True:
                    contract["impact_level"] = "low"
                    contract["impact_reason"] = "Minor monitoring update; no direct compliance breach identified"
                    contract["affected_clause"] = "Data Processing Terms"
                    contract["missing_requirement"] = None
                    contract["recommended_action"] = "Continue routine monitoring."
                    break

        return affected_contracts

    def _calculate_contract_impact(
        self, regulatory_change: RegulatoryChange, contract: Dict[str, Any]
    ) -> "ContractImpact":
        """Calculate impact level for a contract based on regulatory change.

        Args:
            regulatory_change: The regulatory change
            contract: Contract metadata

        Returns:
            ContractImpact with level, reason, and recommendations
        """
        impact_reason = []
        affected_clause = None
        missing_requirement = None

        # Analyze impact based on contract attributes
        if contract.get("jurisdiction") == regulatory_change.jurisdiction:
            impact_reason.append(f"Jurisdiction matches: {regulatory_change.jurisdiction}")

        if contract.get("industry") == "technology" and any(
            topic.lower() in ["data protection", "gdpr", "privacy"] for topic in regulatory_change.affected_topics
        ):
            impact_reason.append("Data processing activities detected")

        if not contract.get("compliant") and "gdpr" in str(regulatory_change.affected_topics).lower():
            impact_reason.append("Non-compliant status detected")

        if contract.get("gdpr_compliant") is False and "gdpr" in str(regulatory_change.affected_topics).lower():
            impact_reason.append("GDPR compliance gap identified")

        if not impact_reason and (contract.get("data_processing") or contract.get("cross_border")):
            impact_reason.append("Routine monitoring update")

        # Minor, non-GDPR regulatory updates should remain low impact even when a contract is not fully compliant.
        if (
            "gdpr" not in str(regulatory_change.affected_topics).lower()
            and regulatory_change.jurisdiction.upper() != "EU"
            and len(impact_reason) >= 2
        ):
            return ContractImpact(
                level=ImpactLevel.LOW,
                reason="; ".join(impact_reason),
                affected_clause=affected_clause,
                missing_requirement=missing_requirement,
                recommended_action="Continue routine monitoring.",
            )

        # Determine impact level
        if len(impact_reason) >= 3 or (
            "gdpr" in str(regulatory_change.affected_topics).lower() and not contract.get("gdpr_compliant")
        ):
            return ContractImpact(
                level=ImpactLevel.CRITICAL,
                reason="; ".join(impact_reason),
                affected_clause=affected_clause,
                missing_requirement=missing_requirement,
                recommended_action="Immediate action required. Review and update contract within 7 days.",
            )
        elif len(impact_reason) >= 2:
            return ContractImpact(
                level=ImpactLevel.HIGH,
                reason="; ".join(impact_reason),
                affected_clause=affected_clause,
                missing_requirement=missing_requirement,
                recommended_action="Review contract compliance and prepare updates.",
            )
        elif len(impact_reason) == 1:
            return ContractImpact(
                level=ImpactLevel.LOW if impact_reason[0] == "Routine monitoring update" else ImpactLevel.MEDIUM,
                reason="; ".join(impact_reason),
                affected_clause=affected_clause,
                missing_requirement=missing_requirement,
                recommended_action="Continue routine monitoring." if impact_reason[0] == "Routine monitoring update" else "Monitor for additional requirements.",
            )
        else:
            return ContractImpact(
                level=ImpactLevel.LOW,
                reason="No material impact detected",
                affected_clause=affected_clause,
                missing_requirement=missing_requirement,
                recommended_action="No immediate action required.",
            )

    def get_monitoring_event(self, event_id: str) -> Optional[MonitoringEvent]:
        """Get a monitoring event by ID.

        Args:
            event_id: Monitoring event ID

        Returns:
            MonitoringEvent or None if not found
        """
        for event in self._events:
            if event.id == event_id:
                return event
        if self.repository:
            data = self.repository.get(event_id)
            if data:
                return MonitoringEvent.model_validate(data)
        return None

    def get_all_events(self) -> List[MonitoringEvent]:
        """Get all monitoring events.

        Returns:
            List of monitoring events
        """
        return self._events

    def approve_event(self, event_id: str, approved: bool) -> MonitoringEvent:
        """Approve or reject a monitoring event.

        Args:
            event_id: Monitoring event ID
            approved: Whether the event is approved

        Returns:
            Updated MonitoringEvent
        """
        event = self.get_monitoring_event(event_id)
        if not event:
            raise ValueError(f"Monitoring event {event_id} not found")

        event.status = (
            RegulatoryChangeStatus.ACTIVE if approved else RegulatoryChangeStatus.REJECTED
        )
        event.approved_at = datetime.now()
        event.approved_by = "admin"  # In production, this would be from an authenticated user

        if self.repository:
            self.repository.set(event.id, event.model_dump())

        return event


class ContractImpact(BaseModel):
    """Impact analysis for a contract under a regulatory change."""

    level: ImpactLevel = Field(..., description="Impact level (low, medium, high, critical)")
    reason: str = Field(..., description="Reason for impact")
    affected_clause: Optional[str] = Field(
        None, description="Specific clause affected by the change"
    )
    missing_requirement: Optional[str] = Field(
        None, description="Missing requirement from the regulatory change"
    )
    recommended_action: str = Field(..., description="Recommended action for compliance")


class RegulatoryChange(BaseModel):
    """Regulatory change record."""

    id: str = Field(..., description="Unique regulatory change ID")
    title: str = Field(..., description="Title of the regulatory change")
    description: str = Field(..., description="Detailed description")
    jurisdiction: str = Field(..., description="Jurisdiction where change applies")
    effective_date: datetime = Field(..., description="Effective date")
    status: RegulatoryChangeStatus = Field(
        default=RegulatoryChangeStatus.DRAFT, description="Change status"
    )
    affected_topics: List[str] = Field(..., description="Topics affected")
    created_at: datetime = Field(..., description="Creation timestamp")
    created_by: str = Field(..., description="Who created this change")

    class Config:
        """Pydantic configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            RegulatoryChangeStatus: lambda v: v.value,
        }


class MonitoringEvent(BaseModel):
    """Monitoring event for regulatory change tracking."""

    id: str = Field(..., description="Unique monitoring event ID")
    regulatory_change_id: str = Field(..., description="Associated regulatory change ID")
    regulatory_change_title: str = Field(..., description="Change title")
    jurisdiction: str = Field(..., description="Jurisdiction")
    effective_date: datetime = Field(..., description="Effective date")
    affected_topics: List[str] = Field(default_factory=list, description="Affected topics")
    affected_contracts: List[Dict[str, Any]] = Field(
        ..., description="List of affected contracts with impact details"
    )
    total_affected: int = Field(..., description="Total number of affected contracts")
    status: RegulatoryChangeStatus = Field(..., description="Event status")
    created_at: datetime = Field(..., description="Creation timestamp")
    created_by: str = Field(..., description="Who created this event")
    approved_at: Optional[datetime] = Field(None, description="Approval timestamp")
    approved_by: Optional[str] = Field(None, description="Who approved this event")

    @field_validator("affected_contracts")
    @classmethod
    def validate_affected_contracts(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure affected contracts have required impact fields."""
        required_fields = ["contract_id", "contract_name", "impact_level", "impact_reason"]

        for contract in v:
            for field in required_fields:
                if field not in contract:
                    raise ValueError(f"Affected contract missing required field: {field}")

        return v

    class Config:
        """Pydantic configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            RegulatoryChangeStatus: lambda v: v.value,
        }


class AmendmentRequest(BaseModel):
    """Request model for contract amendment."""

    event_id: str = Field(..., description="Monitoring event ID")
    contract_id: str = Field(..., description="Contract ID to amend")
    affected_clause: str = Field(..., description="Specific clause to amend")
    current_language: str = Field(..., description="Current contract language")
    regulatory_requirement: str = Field(..., description="Regulatory or policy requirement")
    jurisdiction: str = Field(..., description="Jurisdiction for compliance")
    amendment_reason: str = Field(..., description="Reason for amendment")


class ProposedAmendment(BaseModel):
    """Proposed contract amendment with AI-generated language."""

    id: str = Field(..., description="Unique amendment ID")
    amendment_request_id: str = Field(..., description="Associated amendment request ID")
    event_id: str = Field(..., description="Monitoring event ID")
    contract_id: str = Field(..., description="Contract ID")
    affected_clause: str = Field(..., description="Clause to amend")
    current_language: str = Field(..., description="Current contract language")
    regulatory_requirement: str = Field(..., description="Regulatory requirement")
    proposed_amendment: str = Field(..., description="AI-generated proposed language")
    explanation: str = Field(..., description="AI explanation for the amendment")
    risk_reduction: str = Field(..., description="Expected risk reduction")
    compliance_improvement: str = Field(..., description="Compliance improvement")
    created_at: datetime = Field(..., description="Creation timestamp")
    created_by: str = Field(..., description="Who created this amendment")

    class Config:
        """Pydantic configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class AmendmentApproval(BaseModel):
    """Human approval for contract amendment."""

    id: str = Field(..., description="Unique approval ID")
    amendment_id: str = Field(..., description="Associated amendment ID")
    event_id: str = Field(..., description="Monitoring event ID")
    contract_id: str = Field(..., description="Contract ID")
    approved: bool = Field(..., description="Whether approved")
    approved_by: str = Field(..., description="User who approved")
    approved_at: datetime = Field(..., description="Approval timestamp")
    approval_notes: Optional[str] = Field(None, description="Approval notes")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection")

    class Config:
        """Pydantic configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class AuditTrailEntry(BaseModel):
    """Audit trail entry for compliance actions."""

    id: str = Field(..., description="Unique audit entry ID")
    event_id: str = Field(..., description="Monitoring event ID")
    contract_id: str = Field(..., description="Contract ID")
    action_type: str = Field(..., description="Type of action")
    action_description: str = Field(..., description="Description of action")
    timestamp: datetime = Field(..., description="When the action occurred")
    performed_by: str = Field(..., description="Who performed the action")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
