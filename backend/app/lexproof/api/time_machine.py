"""Blockchain-backed Contract Time Machine APIs."""

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..domains.passport.api.router import get_read_passport_service
from ..services.auth import get_current_user
from ..services.blockchain import create_blockchain_service
from ..services.version_comparison import Clause, VersionComparisonEngine

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/time-machine", tags=["contract-time-machine"])
engine = VersionComparisonEngine()


class VersionComparisonResponse(BaseModel):
    contract_id: str
    version_from: int
    version_to: int
    total_clauses: int
    unchanged_clauses: int
    added_clauses: int
    removed_clauses: int
    modified_clauses: int
    clause_changes: List[Dict[str, Any]]
    risk_delta: float
    compliance_delta: float
    policy_delta: str
    business_impact: str
    blockchain_proof_verified: bool


class VersionHistoryResponse(BaseModel):
    contract_id: str
    versions: List[Dict[str, Any]]


class VersionHistoryVerificationResponse(BaseModel):
    contract_id: str
    verified: bool
    versions: List[Dict[str, Any]]


def _hash_bytes(value: str) -> bytes:
    normalized = value.removeprefix("0x")
    if len(normalized) != 64:
        raise ValueError("Passport hashes must be 32-byte hexadecimal values")
    return bytes.fromhex(normalized)


async def _passports(contract_id: str, user: dict[str, Any]):
    service = get_read_passport_service(user)
    summaries = await service.list_passports(contract_id=contract_id, limit=1000)
    passports = []
    for summary in summaries:
        passport = await service.get_passport(summary.passport_id)
        if passport:
            passports.append(passport)
    return passports


def _clauses(passport: Any) -> List[Clause]:
    raw_clauses = passport.metadata.get("clauses", [])
    if not isinstance(raw_clauses, list):
        raise HTTPException(status_code=422, detail="Passport does not contain structured clause data")
    clauses = []
    for item in raw_clauses:
        if not isinstance(item, dict) or not all(key in item for key in ("text", "hash")):
            raise HTTPException(status_code=422, detail="Malformed clause data in passport")
        clauses.append(Clause(
            text=str(item["text"]), hash=str(item["hash"]),
            risk_score=float(item.get("risk_score", 0)),
            compliance_score=float(item.get("compliance_score", 0)),
            metadata={"clause_id": item.get("clause_id", item["hash"])},
        ))
    return clauses


async def _verify_passport(passport: Any) -> bool:
    hashes = tuple(_hash_bytes(getattr(passport, name)) for name in (
        "document_hash", "policy_hash", "analysis_hash", "evidence_hash"
    ))

    def _verify_sync() -> bool:
        # BlockchainService construction (RPC round-trip) and the on-chain
        # verify_proof call are both blocking web3.py calls; run them on a
        # worker thread so a slow/hung RPC doesn't stall the event loop and,
        # with it, every other request (see status-and-plan.md §2c/§11f).
        # This is also called once per passport version by version_history()
        # below, so without this a contract with several versions serializes
        # several blocking RPC round-trips on the one event loop.
        blockchain = create_blockchain_service()
        proof_id = blockchain.proof_id_for_hashes(*hashes)
        return blockchain.verify_proof(proof_id, *hashes)

    return await asyncio.to_thread(_verify_sync)


def _record(passport: Any, verified: bool) -> Dict[str, Any]:
    return {
        "passport_id": passport.passport_id,
        "version": passport.contract_version,
        "document_hash": passport.document_hash,
        "policy_hash": passport.policy_hash,
        "analysis_hash": passport.analysis_hash,
        "evidence_hash": passport.evidence_hash,
        "risk_score": passport.risk_score,
        "compliance_score": passport.compliance_score,
        "policy_version": passport.policy_version,
        "created_at": passport.created_at,
        "blockchain_proof_verified": verified,
    }


@router.get("/history/{contract_id}", response_model=VersionHistoryResponse)
async def version_history(
    contract_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> VersionHistoryResponse:
    passports = await _passports(contract_id, user)
    if not passports:
        raise HTTPException(status_code=404, detail="No passport versions found")
    # History listing must not block the event loop on Sepolia RPC. On-chain
    # status is filled in by POST /verify-version-history when the user asks.
    versions = [
        _record(passport, verified=False)
        for passport in sorted(passports, key=lambda item: item.contract_version)
    ]
    return VersionHistoryResponse(contract_id=contract_id, versions=versions)


@router.get("/compare", response_model=VersionComparisonResponse)
async def compare_versions(
    contract_id: str,
    version_from: int = Query(..., ge=1),
    version_to: int = Query(..., ge=1),
    user: dict[str, Any] = Depends(get_current_user),
) -> VersionComparisonResponse:
    if version_from == version_to:
        raise HTTPException(status_code=400, detail="Versions must be different")
    passports = {p.contract_version: p for p in await _passports(contract_id, user)}
    previous, current = passports.get(version_from), passports.get(version_to)
    if not previous or not current:
        raise HTTPException(status_code=404, detail="Both passport versions are required")
    # Compare is a Firestore/passport read plus local clause diff. On-chain
    # checks stay on POST /verify-version-history so a Sepolia hang cannot
    # stall a demo the moment someone clicks Compare.
    comparison = engine.compare_versions(
        contract_id, version_from, version_to, _clauses(previous), _clauses(current),
        previous.policy_version, current.policy_version, previous.risk_score,
        current.risk_score, previous.compliance_score, current.compliance_score,
    )
    comparison.blockchain_proof_verified = False
    summary = engine.get_summary(comparison)
    return VersionComparisonResponse(
        contract_id=summary["contract_id"],
        version_from=summary["version_from"],
        version_to=summary["version_to"],
        total_clauses=summary["total_clauses"],
        unchanged_clauses=summary["unchanged"],
        added_clauses=summary["added"],
        removed_clauses=summary["removed"],
        modified_clauses=summary["modified"],
        clause_changes=engine.get_clause_change_details(comparison),
        risk_delta=summary["risk_delta"],
        compliance_delta=summary["compliance_delta"],
        policy_delta=summary["policy_delta"],
        business_impact=summary["business_impact"],
        blockchain_proof_verified=False,
    )


@router.post("/verify-version-history/{contract_id}", response_model=VersionHistoryVerificationResponse)
async def verify_version_history(
    contract_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> VersionHistoryVerificationResponse:
    passports = await _passports(contract_id, user)
    if not passports:
        raise HTTPException(status_code=404, detail="No passport versions found")
    records = []
    for passport in sorted(passports, key=lambda item: item.contract_version):
        try:
            verified = await _verify_passport(passport)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Blockchain verification unavailable") from exc
        records.append(_record(passport, verified))
    return VersionHistoryVerificationResponse(
        contract_id=contract_id,
        verified=all(item["blockchain_proof_verified"] for item in records),
        versions=records,
    )
