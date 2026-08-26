"""
API routes for LexProof
"""

from .blockchain import router as blockchain_router
from .blockchain import public_verify_router
from .time_machine import router as time_machine_router
from .compliance import router as compliance_router
from .remediation import router as remediation_router
from .contracts import router as contracts_router
from .evidence_anchor import router as evidence_anchor_router

__all__ = ["blockchain_router", "public_verify_router", "time_machine_router", "compliance_router", "remediation_router", "contracts_router", "evidence_anchor_router"]
