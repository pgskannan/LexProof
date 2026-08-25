"""LexProof Legal Passport domain module.

This module provides immutable legal intelligence records for contracts,
including risk assessments, compliance scores, evidence tracking, and
cryptographic fingerprints for provenance.
"""

from .models.contract_passport import (
    ContractPassport,
    ContractPassportCreate,
    ContractPassportResponse,
    ContractPassportSummary,
    ContractPassportUpdate,
    PassportStatus,
)
from .models.evidence_item import (
    EvidenceItem,
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceItemSummary,
    EvidenceItemUpdate,
    EvidenceStatus,
    EvidenceType,
)
from .service import PassportService
from .evidence_service import EvidenceService
from .utils.hashing import (
    compute_sha256_hash,
    hash_document,
    hash_original_document,
    hash_normalized_document,
    hash_policy_version,
    hash_ai_analysis,
    hash_evidence_package,
    hash_evidence_item,
    compute_passport_hash,
    verify_hash_consistency,
    generate_evidence_id,
    generate_passport_id,
)

__all__ = [
    # Models
    "ContractPassport",
    "ContractPassportCreate",
    "ContractPassportResponse",
    "ContractPassportSummary",
    "ContractPassportUpdate",
    "PassportStatus",
    "EvidenceItem",
    "EvidenceItemCreate",
    "EvidenceItemResponse",
    "EvidenceItemSummary",
    "EvidenceItemUpdate",
    "EvidenceStatus",
    "EvidenceType",
    # Services
    "PassportService",
    "EvidenceService",
    # Utilities
    "compute_sha256_hash",
    "hash_document",
    "hash_policy_version",
    "hash_ai_analysis",
    "hash_evidence_package",
    "hash_evidence_item",
    "compute_passport_hash",
    "verify_hash_consistency",
    "generate_evidence_id",
    "generate_passport_id",
]
