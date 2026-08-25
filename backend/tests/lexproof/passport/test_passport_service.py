"""Integration tests for PassportService."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.lexproof.domains.passport.models import (
    ContractPassportCreate,
    EvidenceItemCreate,
    EvidenceItemUpdate,
    PassportStatus,
)
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.domains.passport.evidence_service import EvidenceService


class TestPassportService:
    """Test PassportService functionality."""

    @pytest.fixture
    def mock_ai_repo(self):
        """Create mock AI repository."""
        mock_repo = AsyncMock(return_value={
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 82.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding 1",
                    "evidence": "Evidence 1",
                    "recommendation": "Recommendation 1",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote 1",
                },
                {
                    "title": "Finding 2",
                    "severity": "medium",
                    "description": "Test finding 2",
                    "evidence": "Evidence 2",
                    "recommendation": "Recommendation 2",
                    "risk_impact": 45.0,
                    "compliance_impact": 20.0,
                    "source_section": "Section 2",
                    "evidence_quote": "Quote 2",
                },
            ],
            "key_clauses": ["Clause 1", "Clause 2"],
            "compliance_items": ["GDPR Compliance", "Consumer Protection"],
        })
        return mock_repo

    @pytest.fixture
    def mock_event_bus(self):
        """Create mock event bus."""
        return MagicMock()

    @pytest.fixture
    def mock_user(self):
        """Create mock user context."""
        return "test-user-123"

    @pytest.fixture
    def mock_audit_trail(self):
        """Create mock audit trail service."""
        return AsyncMock()

    @pytest.fixture
    def passport_service(
        self,
        mock_ai_repo,
        mock_event_bus,
        mock_user,
        mock_audit_trail,
    ):
        """Create PassportService instance."""
        return PassportService(
            analysis_engine=mock_ai_repo,
            user_id=mock_user,
            tenant_id="test-tenant-123",
            audit_sink=mock_audit_trail,
        )

    @pytest.mark.asyncio
    async def test_create_passport_success(self, passport_service):
        """Test successful passport creation."""
        # Mock analysis trigger
        passport_service.analysis_engine = AsyncMock(return_value={
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 82.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding 1",
                    "evidence": "Evidence 1",
                    "recommendation": "Recommendation 1",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote 1",
                },
                {
                    "title": "Finding 2",
                    "severity": "medium",
                    "description": "Test finding 2",
                    "evidence": "Evidence 2",
                    "recommendation": "Recommendation 2",
                    "risk_impact": 45.0,
                    "compliance_impact": 20.0,
                    "source_section": "Section 2",
                    "evidence_quote": "Quote 2",
                },
            ],
            "key_clauses": ["Clause 1", "Clause 2"],
            "compliance_items": ["GDPR Compliance", "Consumer Protection"],
        })

        # Create passport
        passport = await passport_service.create_passport(
            contract_id="test-contract-1",
            contract_version=1,
            policy_version="1.0.0",
            document_content="Test contract content",
        )

        # Verify passport was created
        assert passport.contract_id == "test-contract-1"
        assert passport.contract_version == 1
        assert passport.risk_score == 75.0
        assert passport.compliance_score == 82.0
        assert passport.policy_version == "1.0.0"
        assert passport.evidence_count > 0
        assert passport.status == PassportStatus.CREATED
        assert len(passport.audit_events) > 0

    @pytest.mark.asyncio
    async def test_create_passport_with_analysis_failure(self, passport_service):
        """Test passport creation with analysis failure."""
        # Mock analysis failure
        passport_service.analysis_engine = AsyncMock(
            side_effect=ValueError("Analysis failed")
        )

        # Attempt to create passport
        with pytest.raises(ValueError, match="Passport creation failed: Analysis failed"):
            await passport_service.create_passport(
                contract_id="test-contract-1",
                contract_version=1,
                policy_version="1.0.0",
                document_content="Test contract content",
            )

    @pytest.mark.asyncio
    async def test_get_passport_missing(self, passport_service):
        """Test that an unknown passport returns None."""
        result = await passport_service.get_passport("test-passport-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_passport_by_contract_missing(self, passport_service):
        """Test that an unknown contract passport returns None."""
        result = await passport_service.get_passport_by_contract(
            contract_id="missing-contract",
            contract_version=1,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_list_passports_empty_filter(self, passport_service):
        """Test that an unmatched contract filter returns no passports."""
        result = await passport_service.list_passports(contract_id="missing-contract")
        assert result == []


class TestEvidenceService:
    """Test EvidenceService functionality."""

    @pytest.fixture
    def evidence_service(self):
        """Create EvidenceService instance."""
        return EvidenceService()

    @pytest.fixture
    def mock_user(self):
        """Create mock user context."""
        return "test-user-123"

    @pytest.mark.asyncio
    async def test_create_evidence_item(self, evidence_service, mock_user):
        """Test evidence item creation."""
        evidence_data = EvidenceItemCreate(
            passport_id="test-passport-1",
            evidence_type="clause",
            title="Test Evidence",
            description="Test description",
            content="Test content",
            content_type="text/plain",
            risk_impact=25.0,
            compliance_impact=15.0,
            evidence_status="valid",
            contract_reference="Section 5.1",
            policy_reference="Policy-123",
            analysis_reference="finding-1",
            source="ai_analysis",
            source_id="finding-1",
        )

        evidence = await evidence_service.create_evidence_item(
            passport_id="test-passport-1",
                evidence_data=evidence_data,
                user="test-user-123",
        )

        assert evidence.evidence_id is not None
        assert evidence.title == "Test Evidence"
        assert evidence.evidence_type.value == "clause"
        assert evidence.risk_impact == 25.0
        assert evidence.passport_id == "test-passport-1"

    @pytest.mark.asyncio
    async def test_get_evidence_item(self, evidence_service):
        """Test retrieving an evidence item."""
        # Create an evidence item first
        evidence_data = EvidenceItemCreate(
            passport_id="test-passport-1",
            evidence_type="clause",
            title="Test Evidence",
            content="Test content",
            content_type="text/plain",
            source="ai_analysis",
        )

        created = await evidence_service.create_evidence_item(
            passport_id="test-passport-1",
            evidence_data=evidence_data,
            user="user-1",
        )

        # Retrieve the evidence item
        retrieved = await evidence_service.get_evidence_item(created.evidence_id)

        assert retrieved is not None
        assert retrieved.evidence_id == created.evidence_id
        assert retrieved.title == "Test Evidence"

    @pytest.mark.asyncio
    async def test_get_evidence_by_passport(self, evidence_service):
        """Test retrieving all evidence for a passport."""
        # Create multiple evidence items
        for i in range(3):
            evidence_data = EvidenceItemCreate(
                passport_id="test-passport-1",
                evidence_type="clause",
                title=f"Test Evidence {i+1}",
                content=f"Test content {i+1}",
                content_type="text/plain",
                source="ai_analysis",
            )

            await evidence_service.create_evidence_item(
                passport_id="test-passport-1",
                    evidence_data=evidence_data,
                    user="user-1",
            )

        # Retrieve all evidence for passport
        evidence_items = await evidence_service.get_evidence_by_passport("test-passport-1")

        assert len(evidence_items) == 3
        assert all(item.evidence_id for item in evidence_items)

    @pytest.mark.asyncio
    async def test_update_evidence_item(self, evidence_service):
        """Test updating an evidence item."""
        # Create an evidence item
        evidence_data = EvidenceItemCreate(
            passport_id="test-passport-1",
            evidence_type="clause",
            title="Test Evidence",
            content="Test content",
            content_type="text/plain",
            source="ai_analysis",
        )

        created = await evidence_service.create_evidence_item(
            passport_id="test-passport-1",
            evidence_data=evidence_data,
            user="user-1",
        )

        # Update the evidence item
        update_data = EvidenceItemUpdate(
            evidence_status="suspicious",
            verified_at=datetime.utcnow(),
        )

        updated = await evidence_service.update_evidence_item(
            evidence_id=created.evidence_id,
            update_data=update_data,
        )

        assert updated is not None
        assert updated.evidence_status.value == "suspicious"
        assert updated.verified_at is not None

    @pytest.mark.asyncio
    async def test_delete_evidence_item(self, evidence_service):
        """Test deleting an evidence item."""
        # Create an evidence item
        evidence_data = EvidenceItemCreate(
            passport_id="test-passport-1",
            evidence_type="clause",
            title="Test Evidence",
            content="Test content",
            content_type="text/plain",
            source="ai_analysis",
        )

        created = await evidence_service.create_evidence_item(
            passport_id="test-passport-1",
            evidence_data=evidence_data,
            user="user-1",
        )

        # Delete the evidence item
        success = await evidence_service.delete_evidence_item(created.evidence_id)

        assert success is True

        # Verify deletion
        retrieved = await evidence_service.get_evidence_item(created.evidence_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_verify_evidence_item(self, evidence_service):
        """Test verifying an evidence item."""
        # Create an evidence item
        evidence_data = EvidenceItemCreate(
            passport_id="test-passport-1",
            evidence_type="clause",
            title="Test Evidence",
            content="Test content",
            content_type="text/plain",
            source="ai_analysis",
        )

        created = await evidence_service.create_evidence_item(
            passport_id="test-passport-1",
            evidence_data=evidence_data,
            user="user-1",
        )

        # Verify the evidence item
        verification_data = {"verified_by": "admin", "verification_method": "manual"}
        verified = await evidence_service.verify_evidence_item(
            evidence_id=created.evidence_id,
            verification_data=verification_data,
        )

        assert verified is not None
        assert verified.verified_at is not None
        assert verified.metadata.get("verified_at") is not None
        assert verified.metadata.get("verification_data") == verification_data

    @pytest.mark.asyncio
    async def test_get_evidence_statistics(self, evidence_service):
        """Test getting evidence statistics."""
        # Create multiple evidence items with different types
        for i in range(2):
            evidence_data = EvidenceItemCreate(
                passport_id="test-passport-1",
                evidence_type="clause",
                title=f"Test Evidence {i+1}",
                content=f"Test content {i+1}",
                content_type="text/plain",
                source="ai_analysis",
            )

            await evidence_service.create_evidence_item(
                passport_id="test-passport-1",
                evidence_data=evidence_data,
                user="user-1",
            )

        # Create a metadata evidence item
        metadata_data = EvidenceItemCreate(
            passport_id="test-passport-1",
            evidence_type="metadata",
            title="Metadata Evidence",
            content="Test metadata",
            content_type="application/json",
            source="ai_analysis",
        )

        await evidence_service.create_evidence_item(
            passport_id="test-passport-1",
            evidence_data=metadata_data,
                user="user-1",
        )

        # Get statistics
        stats = await evidence_service.get_evidence_statistics("test-passport-1")

        assert stats["total_count"] == 2
        assert stats["legal_findings_count"] == 2
        assert "type_counts" in stats
        assert "status_counts" in stats
        assert "avg_risk_impact" in stats
        assert "avg_compliance_impact" in stats
