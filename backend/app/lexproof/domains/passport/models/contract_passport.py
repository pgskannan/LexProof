"""ContractPassport domain model for immutable legal intelligence records.

A ContractPassport is an immutable snapshot of a contract's legal intelligence,
including risk scores, compliance status, evidence, and cryptographic fingerprints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class PassportStatus(str, Enum):
    """Status of a contract passport."""

    PENDING = "pending"
    CREATED = "created"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ContractPassport(BaseModel):
    """Immutable contract passport with all intelligence data.

    This model represents a snapshot of a contract's legal intelligence,
    including risk scores, compliance status, evidence, and cryptographic
    fingerprints for provenance tracking.
    """

    # Core identification
    passport_id: str = Field(..., description="Unique passport identifier")
    contract_id: str = Field(..., description="Parent contract identifier")
    contract_version: int = Field(..., ge=1, description="Contract version number")

    # Cryptographic fingerprints (deterministic SHA-256 hashes)
    document_hash: str = Field(..., description="SHA-256 hash of original document")
    policy_hash: str = Field(..., description="SHA-256 hash of applied policy")
    analysis_hash: str = Field(..., description="SHA-256 hash of AI analysis result")
    evidence_hash: str = Field(..., description="SHA-256 hash of evidence package")

    # Risk assessment
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Overall risk score (0-100)")
    compliance_score: float = Field(..., ge=0.0, le=100.0, description="Compliance score (0-100)")

    # Policy and evidence metadata
    policy_version: str = Field(..., description="Policy version identifier")
    evidence_count: int = Field(..., ge=0, description="Number of evidence items")

    # Timestamps
    created_at: datetime = Field(..., description="Passport creation timestamp")
    created_by: str = Field(..., description="User who created this passport")

    # Status
    status: PassportStatus = Field(
        default=PassportStatus.PENDING, description="Passport status"
    )

    # Real, measured AI processing time (hardening item #3): the actual elapsed
    # wall-clock time of the Gemini analysis call that produced this passport's
    # analysis_result, timed directly around that call in version_analysis.py.
    # Deliberately NOT derived from broader lifecycle timestamps (contract
    # version created_at vs. passport created_at), which can include upload
    # delay, developer debugging/restarts, or re-analysis gaps and therefore
    # overstate or understate true AI processing time. None for passports
    # created before this field existed, or on the rare idempotent path where
    # an existing analysis_snapshot was reused instead of calling Gemini again.
    ai_analysis_duration_ms: Optional[float] = Field(
        default=None,
        description="Measured wall-clock duration (ms) of the actual Gemini analysis call",
    )

    # Audit trail
    audit_events: List[Dict[str, Any]] = Field(
        default_factory=list, description="Immutable audit trail"
    )

    # Additional metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional passport metadata"
    )

    @field_validator("audit_events")
    @classmethod
    def validate_audit_events(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure audit events are immutable and ordered by timestamp."""
        if not v:
            return []

        # Check that events are ordered by timestamp (earliest first)
        timestamps = [event.get("timestamp") for event in v if "timestamp" in event]
        if timestamps:
            for i in range(1, len(timestamps)):
                if timestamps[i] < timestamps[i - 1]:
                    raise ValueError("Audit events must be ordered by timestamp")

        return v

    class Config:
        """Pydantic configuration for immutability and JSON schema."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            PassportStatus: lambda v: v.value,
        }
        frozen = True  # Make model immutable after creation
        use_enum_values = True
        validate_assignment = False  # Prevent modification after creation


class ContractPassportCreate(BaseModel):
    """Schema for creating a new contract passport."""

    contract_id: str = Field(..., description="Contract identifier")
    contract_version: int = Field(..., ge=1, description="Contract version number")
    policy_version: str = Field(..., description="Policy version identifier")
    created_by: str = Field(..., description="User creating the passport")
    document_content: str = Field(..., min_length=1, description="Original document content")
    normalized_document: str = Field(default="", description="Normalized document content")
    policy_content: str = Field(default="", description="Policy content used for analysis")

    @field_validator("contract_id")
    @classmethod
    def contract_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Contract ID must not be empty")
        return v.strip()


class ContractPassportUpdate(BaseModel):
    """Schema retained for compatibility; snapshots cannot be updated."""

    status: PassportStatus = Field(..., description="New passport status")



class ContractPassportResponse(BaseModel):
    """Schema for passport response (read-only)."""

    passport_id: str
    contract_id: str
    contract_version: int
    document_hash: str
    policy_hash: str
    analysis_hash: str
    evidence_hash: str
    risk_score: float
    compliance_score: float
    policy_version: str
    evidence_count: int
    created_at: datetime
    created_by: str
    status: PassportStatus
    ai_analysis_duration_ms: Optional[float] = None
    audit_events: List[Dict[str, Any]]
    metadata: Dict[str, Any]

    class Config:
        """Pydantic configuration for serialization."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            PassportStatus: lambda v: v.value,
        }


class ContractPassportSummary(BaseModel):
    """Schema for passport summary (lightweight listing)."""

    passport_id: str
    contract_id: str
    contract_version: int
    risk_score: float
    compliance_score: float
    policy_version: str
    evidence_count: int
    created_at: datetime
    status: PassportStatus
    ai_analysis_duration_ms: Optional[float] = None

    class Config:
        """Pydantic configuration for serialization."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            PassportStatus: lambda v: v.value,
        }
