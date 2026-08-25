"""Unit tests for ContractPassport and EvidenceItem models."""

import pytest
from datetime import datetime

from app.lexproof.domains.passport.models.contract_passport import (
    ContractPassport,
    ContractPassportCreate,
    ContractPassportResponse,
    ContractPassportSummary,
    PassportStatus,
)
from app.lexproof.domains.passport.models.evidence_item import (
    EvidenceItem,
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceItemSummary,
    EvidenceItemUpdate,
    EvidenceStatus,
    EvidenceType,
)


class TestContractPassportModels:
    """Test ContractPassport model validation and serialization."""

    def test_contract_passport_basic_creation(self):
        """Test basic ContractPassport creation."""
        passport = ContractPassport(
            passport_id="test-passport-1",
            contract_id="test-contract-1",
            contract_version=1,
            document_hash="a1b2c3d4e5f6...",
            policy_hash="c3d4e5f6...",
            analysis_hash="e5f6a7b8...",
            evidence_hash="g7h8i9j0...",
            risk_score=75.0,
            compliance_score=82.0,
            policy_version="1.0.0",
            evidence_count=5,
            created_at=datetime.utcnow(),
            created_by="user-123",
            status=PassportStatus.CREATED,
            audit_events=[],
        )

        assert passport.passport_id == "test-passport-1"
        assert passport.contract_id == "test-contract-1"
        assert passport.risk_score == 75.0
        assert passport.compliance_score == 82.0

    def test_contract_passport_immutable_after_creation(self):
        """Test that ContractPassport is frozen after creation."""
        passport = ContractPassport(
            passport_id="test-passport-2",
            contract_id="test-contract-2",
            contract_version=1,
            document_hash="a1b2c3d4e5f6...",
            policy_hash="c3d4e5f6...",
            analysis_hash="e5f6a7b8...",
            evidence_hash="g7h8i9j0...",
            risk_score=75.0,
            compliance_score=82.0,
            policy_version="1.0.0",
            evidence_count=5,
            created_at=datetime.utcnow(),
            created_by="user-123",
            status=PassportStatus.CREATED,
            audit_events=[],
        )

        # Model is frozen, so assignment should fail
        with pytest.raises(Exception):
            passport.passport_id = "different-passport-id"

    def test_contract_passport_status_enum(self):
        """Test PassportStatus enum values."""
        assert PassportStatus.PENDING.value == "pending"
        assert PassportStatus.CREATED.value == "created"
        assert PassportStatus.REVOKED.value == "revoked"
        assert PassportStatus.EXPIRED.value == "expired"

    def test_contract_passport_risk_score_validation(self):
        """Test that risk score is within valid range."""
        with pytest.raises(ValueError):
            ContractPassport(
                passport_id="test-passport-3",
                contract_id="test-contract-3",
                contract_version=1,
                document_hash="a1b2c3d4e5f6...",
                policy_hash="c3d4e5f6...",
                analysis_hash="e5f6a7b8...",
                evidence_hash="g7h8i9j0...",
                risk_score=-1.0,  # Invalid: less than 0
                compliance_score=82.0,
                policy_version="1.0.0",
                evidence_count=5,
                created_at=datetime.utcnow(),
                created_by="user-123",
                status=PassportStatus.CREATED,
                audit_events=[],
            )

        with pytest.raises(ValueError):
            ContractPassport(
                passport_id="test-passport-4",
                contract_id="test-contract-4",
                contract_version=1,
                document_hash="a1b2c3d4e5f6...",
                policy_hash="c3d4e5f6...",
                analysis_hash="e5f6a7b8...",
                evidence_hash="g7h8i9j0...",
                risk_score=101.0,  # Invalid: greater than 100
                compliance_score=82.0,
                policy_version="1.0.0",
                evidence_count=5,
                created_at=datetime.utcnow(),
                created_by="user-123",
                status=PassportStatus.CREATED,
                audit_events=[],
            )


class TestEvidenceItemModels:
    """Test EvidenceItem model validation and serialization."""

    def test_evidence_item_basic_creation(self):
        """Test basic EvidenceItem creation."""
        evidence = EvidenceItem(
            evidence_id="test-evidence-1",
            passport_id="test-passport-1",
            evidence_type=EvidenceType.CLAUSE,
            title="Test Evidence",
            description="Test description",
            content="Test content",
            content_type="text/plain",
            risk_impact=25.0,
            compliance_impact=15.0,
            evidence_status=EvidenceStatus.VALID,
            contract_reference="Section 5.1",
            policy_reference="Policy-123",
            analysis_reference="finding-1",
            created_at=datetime.utcnow(),
            verified_at=None,
            source="ai_analysis",
            source_id="finding-1",
            hash="a1b2c3d4e5f6789012345678901234567890abcdefabcdefabcdefabcdefabcd",
            metadata={},
        )

        assert evidence.evidence_id == "test-evidence-1"
        assert evidence.evidence_type == EvidenceType.CLAUSE
        assert evidence.risk_impact == 25.0

    def test_evidence_item_status_enum(self):
        """Test EvidenceStatus enum values."""
        assert EvidenceStatus.VALID.value == "valid"
        assert EvidenceStatus.SUSPICIOUS.value == "suspicious"
        assert EvidenceStatus.INVALID.value == "invalid"
        assert EvidenceStatus.PENDING.value == "pending"

    def test_evidence_item_type_enum(self):
        """Test EvidenceType enum values."""
        assert EvidenceType.CLAUSE.value == "clause"
        assert EvidenceType.REDLINE.value == "redline"
        assert EvidenceType.POLICY_MATCH.value == "policy_match"
        assert EvidenceType.AUDIT_LOG.value == "audit_log"
        assert EvidenceType.METADATA.value == "metadata"
        assert EvidenceType.ATTACHMENT.value == "attachment"
        assert EvidenceType.OTHER.value == "other"

    def test_evidence_item_hash_validation(self):
        """Test that hash must be 64-character hex string."""
        with pytest.raises(ValueError):
            EvidenceItem(
                evidence_id="test-evidence-2",
                passport_id="test-passport-2",
                evidence_type=EvidenceType.CLAUSE,
                title="Test Evidence",
                content="Test content",
                content_type="text/plain",
                risk_impact=25.0,
                compliance_impact=15.0,
                evidence_status=EvidenceStatus.VALID,
                contract_reference="Section 5.1",
                policy_reference="Policy-123",
                analysis_reference="finding-1",
                created_at=datetime.utcnow(),
                verified_at=None,
                source="ai_analysis",
                source_id="finding-1",
                hash="invalid",  # Invalid: not 64 characters
                metadata={},
            )

    def test_evidence_item_content_type_validation(self):
        """Test that content type is not empty."""
        with pytest.raises(ValueError):
            EvidenceItem(
                evidence_id="test-evidence-3",
                passport_id="test-passport-3",
                evidence_type=EvidenceType.CLAUSE,
                title="Test Evidence",
                content="Test content",
                content_type="",  # Invalid: empty
                risk_impact=25.0,
                compliance_impact=15.0,
                evidence_status=EvidenceStatus.VALID,
                contract_reference="Section 5.1",
                policy_reference="Policy-123",
                analysis_reference="finding-1",
                created_at=datetime.utcnow(),
                verified_at=None,
                source="ai_analysis",
                source_id="finding-1",
                hash="a1b2c3d4e5f6...",
                metadata={},
            )


class TestCreateSchemas:
    """Test creation schema validation."""

    def test_contract_passport_create_validation(self):
        """Test ContractPassportCreate schema validation."""
        create_schema = ContractPassportCreate(
            contract_id="test-contract-1",
            contract_version=1,
            policy_version="1.0.0",
            created_by="user-123",
            document_content="Test contract content",
        )

        assert create_schema.contract_id == "test-contract-1"
        assert create_schema.contract_version == 1

    def test_evidence_item_create_validation(self):
        """Test EvidenceItemCreate schema validation."""
        create_schema = EvidenceItemCreate(
            passport_id="test-passport-1",
            evidence_type=EvidenceType.CLAUSE,
            title="Test Evidence",
            content="Test content",
            content_type="text/plain",
            risk_impact=25.0,
            compliance_impact=15.0,
            evidence_status=EvidenceStatus.VALID,
            contract_reference="Section 5.1",
            policy_reference="Policy-123",
            analysis_reference="finding-1",
            source="ai_analysis",
            source_id="finding-1",
        )

        assert create_schema.evidence_type == EvidenceType.CLAUSE
        assert create_schema.risk_impact == 25.0

    def test_contract_id_not_empty_validation(self):
        """Test that contract_id cannot be empty."""
        with pytest.raises(ValueError):
            ContractPassportCreate(
                contract_id="",  # Invalid: empty
                contract_version=1,
                policy_version="1.0.0",
                created_by="user-123",
            )

    def test_title_not_empty_validation(self):
        """Test that title cannot be empty."""
        with pytest.raises(ValueError):
            EvidenceItemCreate(
                passport_id="test-passport-1",
                evidence_type=EvidenceType.CLAUSE,
                title="",  # Invalid: empty
                content="Test content",
                content_type="text/plain",
                source="ai_analysis",
            )
