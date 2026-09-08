"""EvidenceItem domain model for tracking evidence in legal passports.

Evidence items represent verifiable artifacts that support the legal intelligence
assessment in a ContractPassport, such as clauses, redlines, policy matches, and
audit logs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class EvidenceType(str, Enum):
    """Type of evidence item."""

    CLAUSE = "clause"
    REDLINE = "redline"
    POLICY_MATCH = "policy_match"
    AUDIT_LOG = "audit_log"
    METADATA = "metadata"
    ATTACHMENT = "attachment"
    COUNTERPARTY_COUNTERSIGNATURE = "counterparty_countersignature"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    """Status of evidence item."""

    VALID = "valid"
    SUSPICIOUS = "suspicious"
    INVALID = "invalid"
    PENDING = "pending"


class EvidenceItem(BaseModel):
    """Evidence item supporting contract intelligence assessment.

    Each evidence item provides verifiable proof for specific aspects of the
    contract assessment, including risk findings, compliance checks, and
    policy application.
    """

    # Core identification
    evidence_id: str = Field(..., description="Unique evidence identifier")
    passport_id: str = Field(..., description="Parent passport identifier")
    evidence_type: EvidenceType = Field(..., description="Type of evidence")

    # Evidence content
    title: str = Field(..., description="Human-readable title")
    description: Optional[str] = Field(None, description="Detailed description")
    content: str = Field(..., description="Evidence content (text, JSON, or base64)")
    content_type: str = Field(..., description="MIME type of content")

    # Evidence metadata
    risk_impact: Optional[float] = Field(None, ge=0.0, le=100.0, description="Risk impact score")
    compliance_impact: Optional[float] = Field(None, ge=0.0, le=100.0, description="Compliance impact score")
    evidence_status: EvidenceStatus = Field(
        default=EvidenceStatus.VALID, description="Evidence validity status"
    )

    # References
    contract_reference: Optional[str] = Field(None, description="Contract reference (clause, section)")
    policy_reference: Optional[str] = Field(None, description="Policy reference")
    analysis_reference: Optional[str] = Field(None, description="Reference to AI analysis finding")

    # Timestamps
    created_at: datetime = Field(..., description="Evidence creation timestamp")
    verified_at: Optional[datetime] = Field(None, description="Verification timestamp")

    # Provenance
    source: str = Field(..., description="Source of evidence (e.g., 'ai_analysis', 'manual_review')")
    source_id: Optional[str] = Field(None, description="Source identifier")
    hash: Optional[str] = Field(None, description="SHA-256 hash of evidence content")

    # Additional metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional evidence metadata"
    )

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        """Validate hash format if provided."""
        if v is not None:
            if not isinstance(v, str) or len(v) != 64:
                raise ValueError("Hash must be a SHA-256 hex string (64 characters)")
        return v

    @field_validator("content_type")
    @classmethod
    def content_type_not_empty(cls, v: str) -> str:
        """Ensure content type is not empty."""
        if not v.strip():
            raise ValueError("Content type must not be empty")
        return v.strip()

    class Config:
        """Pydantic configuration for JSON schema."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            EvidenceType: lambda v: v.value,
            EvidenceStatus: lambda v: v.value,
        }
        use_enum_values = True


class EvidenceItemCreate(BaseModel):
    """Schema for creating a new evidence item."""

    passport_id: str = Field(..., description="Parent passport identifier")
    evidence_type: EvidenceType = Field(..., description="Type of evidence")
    title: str = Field(..., description="Evidence title")
    description: Optional[str] = Field(None, description="Detailed description")
    content: str = Field(..., description="Evidence content")
    content_type: str = Field(..., description="MIME type of content")
    risk_impact: Optional[float] = Field(None, ge=0.0, le=100.0, description="Risk impact score")
    compliance_impact: Optional[float] = Field(None, ge=0.0, le=100.0, description="Compliance impact score")
    evidence_status: EvidenceStatus = Field(
        default=EvidenceStatus.VALID, description="Evidence validity status"
    )
    contract_reference: Optional[str] = Field(None, description="Contract reference")
    policy_reference: Optional[str] = Field(None, description="Policy reference")
    analysis_reference: Optional[str] = Field(None, description="Analysis reference")
    source: str = Field(..., description="Source of evidence")
    source_id: Optional[str] = Field(None, description="Source identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title must not be empty")
        return v.strip()


class EvidenceItemUpdate(BaseModel):
    """Schema for updating evidence item (status changes only)."""

    evidence_status: EvidenceStatus = Field(..., description="New evidence status")
    verified_at: Optional[datetime] = Field(None, description="Verification timestamp")


class EvidenceItemResponse(BaseModel):
    """Schema for evidence item response (read-only)."""

    evidence_id: str
    passport_id: str
    evidence_type: EvidenceType
    title: str
    description: Optional[str]
    content: str
    content_type: str
    risk_impact: Optional[float]
    compliance_impact: Optional[float]
    evidence_status: EvidenceStatus
    contract_reference: Optional[str]
    policy_reference: Optional[str]
    analysis_reference: Optional[str]
    created_at: datetime
    verified_at: Optional[datetime]
    source: str
    source_id: Optional[str]
    hash: Optional[str]
    metadata: Dict[str, Any]

    class Config:
        """Pydantic configuration for serialization."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            EvidenceType: lambda v: v.value,
            EvidenceStatus: lambda v: v.value,
        }


class EvidenceItemSummary(BaseModel):
    """Schema for evidence item summary (lightweight listing)."""

    evidence_id: str
    evidence_type: EvidenceType
    title: str
    description: Optional[str] = None
    evidence_status: EvidenceStatus
    risk_impact: Optional[float]
    compliance_impact: Optional[float]
    contract_reference: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    class Config:
        """Pydantic configuration for serialization."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            EvidenceType: lambda v: v.value,
            EvidenceStatus: lambda v: v.value,
        }
