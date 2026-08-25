"""Automated tests for compliance monitoring system."""

import pytest
from datetime import datetime
from typing import Any, Dict

from app.lexproof.domains.compliance.models import (
    ComplianceMonitorService,
    ImpactLevel,
    ContractImpact,
    RegulatoryChange,
    RegulatoryChangeStatus,
    MonitoringEvent,
)


class TestComplianceMonitorService:
    """Test suite for ComplianceMonitorService."""

    def test_simulate_regulatory_change_creates_event(self):
        """Test that simulating a regulatory change creates a monitoring event."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="GDPR Data Protection Update",
            description="New requirements for data processing",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR", "data protection"],
        )

        assert event is not None
        assert event.regulatory_change_title == "GDPR Data Protection Update"
        assert event.jurisdiction == "EU"
        assert event.total_affected >= 0
        assert event.status == RegulatoryChangeStatus.PENDING
        assert len(event.affected_contracts) > 0

    def test_identify_affected_contracts_filters_by_jurisdiction(self):
        """Test that affected contracts are filtered by jurisdiction."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="EU GDPR Update",
            description="GDPR compliance update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # All affected contracts should match EU jurisdiction
        for contract in event.affected_contracts:
            assert contract["jurisdiction"] == "EU"

    def test_identify_affected_contracts_filters_by_topics(self):
        """Test that affected contracts are filtered by affected topics."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="Data Privacy Regulation",
            description="Privacy regulation update",
            jurisdiction="US",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["CCPA", "data protection"],
        )

        # All affected contracts should have data processing or privacy in their metadata
        for contract in event.affected_contracts:
            assert "GDPR" in str(event.affected_topics).lower() or "data" in str(contract).lower()

    def test_calculate_impact_level_high(self):
        """Test that contracts with multiple issues get high impact level."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="Data Protection Regulation",
            description="Data protection requirements",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # Find a contract with high impact
        high_impact_contract = None
        for contract in event.affected_contracts:
            if contract["impact_level"] == "high":
                high_impact_contract = contract
                break

        assert high_impact_contract is not None
        assert high_impact_contract["impact_level"] == "high"

    def test_calculate_impact_level_critical(self):
        """Test that contracts with severe issues get critical impact level."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="GDPR Non-Compliance",
            description="Severe GDPR violations",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # Find a contract with critical impact
        critical_impact_contract = None
        for contract in event.affected_contracts:
            if contract["impact_level"] == "critical":
                critical_impact_contract = contract
                break

        assert critical_impact_contract is not None
        assert critical_impact_contract["impact_level"] == "critical"

    def test_calculate_impact_level_low(self):
        """Test that contracts with minimal issues get low impact level."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="Minor Regulatory Update",
            description="Minor compliance update",
            jurisdiction="US",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["data protection"],
        )

        # Find a contract with low impact
        low_impact_contract = None
        for contract in event.affected_contracts:
            if contract["impact_level"] == "low":
                low_impact_contract = contract
                break

        assert low_impact_contract is not None
        assert low_impact_contract["impact_level"] == "low"

    def test_get_monitoring_event_by_id(self):
        """Test retrieving a monitoring event by ID."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="GDPR Update",
            description="GDPR compliance update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        retrieved_event = service.get_monitoring_event(event.id)

        assert retrieved_event is not None
        assert retrieved_event.id == event.id
        assert retrieved_event.regulatory_change_title == event.regulatory_change_title

    def test_get_monitoring_event_not_found(self):
        """Test that non-existent event returns None."""
        service = ComplianceMonitorService()

        event = service.get_monitoring_event("non-existent-id")

        assert event is None

    def test_get_all_events(self):
        """Test retrieving all monitoring events."""
        service = ComplianceMonitorService()

        # Create multiple events
        for i in range(3):
            service.simulate_regulatory_change(
                title=f"Regulatory Change {i}",
                description=f"Description {i}",
                jurisdiction="EU",
                effective_date=datetime(2024, 1, 1),
                affected_topics=["GDPR"],
            )

        events = service.get_all_events()

        assert len(events) == 3

    def test_approve_event_approves(self):
        """Test that approving an event changes its status."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="GDPR Update",
            description="GDPR compliance update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # Approve the event
        approved_event = service.approve_event(event.id, approved=True)

        assert approved_event.status == RegulatoryChangeStatus.ACTIVE
        assert approved_event.approved_at is not None
        assert approved_event.approved_by == "admin"

    def test_reject_event_rejects(self):
        """Test that rejecting an event changes its status."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="GDPR Update",
            description="GDPR compliance update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # Reject the event
        rejected_event = service.approve_event(event.id, approved=False)

        assert rejected_event.status == RegulatoryChangeStatus.REJECTED
        assert rejected_event.approved_at is not None
        assert rejected_event.approved_by == "admin"

    def test_approve_nonexistent_event_raises_error(self):
        """Test that approving a non-existent event raises ValueError."""
        service = ComplianceMonitorService()

        with pytest.raises(ValueError, match="not found"):
            service.approve_event("non-existent-id", approved=True)

    def test_affected_contracts_have_required_fields(self):
        """Test that all affected contracts have required fields."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="GDPR Update",
            description="GDPR compliance update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # Check all contracts have required fields
        required_fields = [
            "contract_id",
            "contract_name",
            "impact_level",
            "impact_reason",
        ]

        for contract in event.affected_contracts:
            for field in required_fields:
                assert field in contract, f"Contract missing required field: {field}"

    def test_impact_levels_are_valid(self):
        """Test that impact levels are valid enum values."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="Regulatory Change",
            description="Test regulatory change",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # Check all impact levels are valid
        valid_levels = ["low", "medium", "high", "critical"]
        for contract in event.affected_contracts:
            assert contract["impact_level"] in valid_levels

    def test_recommended_action_exists(self):
        """Test that all affected contracts have recommended actions."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="Regulatory Change",
            description="Test regulatory change",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        for contract in event.affected_contracts:
            assert contract["recommended_action"], "Contract missing recommended action"
            assert len(contract["recommended_action"]) > 0

    def test_audit_events_ordered_by_timestamp(self):
        """Test that audit events are ordered by timestamp."""
        service = ComplianceMonitorService()

        event = service.simulate_regulatory_change(
            title="GDPR Update",
            description="GDPR compliance update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_topics=["GDPR"],
        )

        # Get all events
        events = service.get_all_events()

        # Check that events are ordered by creation time
        timestamps = [event.created_at for event in events]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]


class TestImpactLevel:
    """Test suite for ImpactLevel enum."""

    def test_impact_level_values(self):
        """Test that ImpactLevel enum has correct values."""
        assert ImpactLevel.LOW.value == "low"
        assert ImpactLevel.MEDIUM.value == "medium"
        assert ImpactLevel.HIGH.value == "high"
        assert ImpactLevel.CRITICAL.value == "critical"


class TestRegulatoryChangeStatus:
    """Test suite for RegulatoryChangeStatus enum."""

    def test_regulatory_change_status_values(self):
        """Test that RegulatoryChangeStatus enum has correct values."""
        assert RegulatoryChangeStatus.DRAFT.value == "draft"
        assert RegulatoryChangeStatus.PENDING.value == "pending"
        assert RegulatoryChangeStatus.ACTIVE.value == "active"
        assert RegulatoryChangeStatus.RESOLVED.value == "resolved"
        assert RegulatoryChangeStatus.SUPERSEDED.value == "superseded"


class TestContractImpact:
    """Test suite for ContractImpact model."""

    def test_contract_impact_has_all_fields(self):
        """Test that ContractImpact model has all required fields."""
        impact = ContractImpact(
            level=ImpactLevel.HIGH,
            reason="Test reason",
            affected_clause="Clause 5.1",
            missing_requirement="GDPR compliance",
            recommended_action="Update contract",
        )

        assert impact.level == ImpactLevel.HIGH
        assert impact.reason == "Test reason"
        assert impact.affected_clause == "Clause 5.1"
        assert impact.missing_requirement == "GDPR compliance"
        assert impact.recommended_action == "Update contract"


class TestMonitoringEvent:
    """Test suite for MonitoringEvent model."""

    def test_monitoring_event_has_all_fields(self):
        """Test that MonitoringEvent model has all required fields."""
        event = MonitoringEvent(
            id="test-id",
            regulatory_change_id="reg-change-id",
            regulatory_change_title="GDPR Update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_contracts=[
                {
                    "contract_id": "contract-001",
                    "contract_name": "Test Contract",
                    "industry": "technology",
                    "jurisdiction": "EU",
                    "impact_level": "high",
                    "impact_reason": "GDPR non-compliance",
                    "affected_clause": "Data Processing",
                    "missing_requirement": "GDPR compliance",
                    "recommended_action": "Update contract",
                }
            ],
            total_affected=1,
            status=RegulatoryChangeStatus.PENDING,
            created_at=datetime(2024, 1, 1),
            created_by="system",
        )

        assert event.id == "test-id"
        assert event.regulatory_change_title == "GDPR Update"
        assert event.jurisdiction == "EU"
        assert len(event.affected_contracts) == 1
        assert event.total_affected == 1
        assert event.status == RegulatoryChangeStatus.PENDING

    def test_monitoring_event_default_values(self):
        """Test that MonitoringEvent has correct default values."""
        event = MonitoringEvent(
            id="test-id",
            regulatory_change_id="reg-change-id",
            regulatory_change_title="GDPR Update",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            affected_contracts=[],
            total_affected=0,
            status=RegulatoryChangeStatus.PENDING,
            created_at=datetime(2024, 1, 1),
            created_by="system",
        )

        assert event.approved_at is None
        assert event.approved_by is None


class TestRegulatoryChange:
    """Test suite for RegulatoryChange model."""

    def test_regulatory_change_has_all_fields(self):
        """Test that RegulatoryChange model has all required fields."""
        change = RegulatoryChange(
            id="test-id",
            title="GDPR Update",
            description="New GDPR requirements",
            jurisdiction="EU",
            effective_date=datetime(2024, 1, 1),
            status=RegulatoryChangeStatus.PENDING,
            affected_topics=["GDPR", "data protection"],
            created_at=datetime(2024, 1, 1),
            created_by="system",
        )

        assert change.id == "test-id"
        assert change.title == "GDPR Update"
        assert change.jurisdiction == "EU"
        assert change.status == RegulatoryChangeStatus.PENDING
        assert len(change.affected_topics) == 2
