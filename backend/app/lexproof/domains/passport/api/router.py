"""Legal Passport API endpoints.

Provides REST API endpoints for creating, retrieving, and managing
contract passports and evidence items.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..service import PassportService
from ..evidence_service import EvidenceService
from ..models import (
    ContractPassportCreate,
    ContractPassportResponse,
    ContractPassportSummary,
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceItemUpdate,
    EvidenceItemSummary,
    PassportStatus,
)
from ....repositories.firestore import (
    EvidenceAnchorRepository,
    EvidenceRecordRepository,
    FirestoreRepository,
    PassportAnchorRepository,
)
from ....services.auth import get_current_user
from ....services.passport_root_anchor_service import (
    PassportEligibilityError,
    PassportRootConflictError,
    get_passport_root_anchor_service,
)
from ..integrity import verify_passport_integrity
from ..proof_package import build_proof_package

router = APIRouter(prefix="/passports", tags=["Legal Passports"])
contract_router = APIRouter(prefix="/contracts", tags=["Legal Passports"])


# ─────────────────────────────────────────────────────────────────────────────────
# Passport Endpoints
# ─────────────────────────────────────────────────────────────────────────────────

_evidence_anchor_repository = EvidenceAnchorRepository("evidence_anchors")
_evidence_service = EvidenceService(
    EvidenceRecordRepository(_evidence_anchor_repository),
    passport_repository=FirestoreRepository("legal_passports"),
    anchor_repository=_evidence_anchor_repository,
)
# Additive: passport ROOT anchors live in their own collection, never mixed
# into evidence_anchors (see docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md §10).
_passport_anchor_repository = PassportAnchorRepository("passport_anchors")

# What configure_passport_service() actually needs to share across requests is
# the analysis engine + repository the app was armed with at startup (real
# ContractRiskEdge engine + real Firestore in production, an in-memory/test
# double in tests) -- NOT a live PassportService object. A stored
# PassportService carries a baked-in identity (its own user_id/tenant_id),
# and a process-wide "here is THE passport service" singleton with a fake
# identity is exactly the bug class this app has already hit twice: the
# passports list/status tenant-scoping gap and the create_passport auth gap
# (both fixed by building a fresh, correctly-scoped PassportService per
# request instead of reusing a singleton). Storing only the two reusable,
# identity-free fields below removes that footgun structurally -- there is
# no "get me THE passport service" call left anywhere in this module for a
# future endpoint to reach for by mistake; every caller must go through
# get_read_passport_service(user) or get_create_passport_service(user) and
# supply the real signed-in caller's identity.
_configured_analysis_engine: Optional[Any] = None
_configured_repository: Optional[FirestoreRepository] = None
_configured = False


async def _analysis_engine(document: str, policy: str) -> Dict[str, Any]:
    """Adapter boundary for ContractRiskEdge's existing analysis engine.

    Deployments should replace this dependency with the existing AIService
    method; this module never performs a second AI analysis implementation.
    """
    raise RuntimeError("ContractRiskEdge analysis engine adapter is not configured")


def configure_passport_service(service: PassportService) -> None:
    """Capture the analysis engine + repository from a fully-built
    PassportService (real one at application startup, or a test double) for
    reuse by get_create_passport_service. Only those two fields are kept --
    see the module comment above for why the service object itself is never
    stored or exposed.
    """
    global _configured_analysis_engine, _configured_repository, _configured
    _configured_analysis_engine = service.analysis_engine
    _configured_repository = service.repository
    _configured = True


def get_read_passport_service(user: Dict[str, Any]) -> PassportService:
    return PassportService(
        analysis_engine=_analysis_engine,
        user_id=str(user["uid"]),
        tenant_id=str(user["uid"]),
        repository=FirestoreRepository("legal_passports"),
        # Phase 3H.2 (P1-A): lets PassportService resolve a passport's
        # associated Contract's org_id and apply the same org-aware read
        # visibility Contract endpoints already use (see
        # ..authorization.is_visible_via_contract). Built fresh here, like
        # `repository` above, rather than shared as a module-level
        # singleton, so both stay patchable the same way in tests.
        contracts_repository=FirestoreRepository("contracts"),
    )


def get_create_passport_service(user: Dict[str, Any]) -> PassportService:
    """Like get_read_passport_service, but reuses whichever analysis engine
    and repository configure_passport_service() was last called with (real
    engine + real Firestore at application startup, or a test double) rather
    than always building a fresh real FirestoreRepository. create_passport
    actually needs a working engine, unlike the read-only endpoints, and a
    caller that configured an in-memory/test repository (repository=None)
    should keep getting that behavior. User/tenant scoping always comes from
    the real signed-in caller passed in here, never from whatever identity a
    previously-configured PassportService happened to carry, so a passport
    created through this endpoint is correctly attributed.
    """
    if _configured:
        engine = _configured_analysis_engine
        repository = _configured_repository
    else:
        engine = _analysis_engine
        repository = FirestoreRepository("legal_passports")
    return PassportService(
        analysis_engine=engine,
        user_id=str(user["uid"]),
        tenant_id=str(user["uid"]),
        repository=repository,
        contracts_repository=FirestoreRepository("contracts"),
    )


@router.post("", response_model=ContractPassportResponse)
async def create_passport(
    body: ContractPassportCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new legal passport for a contract.

    This endpoint triggers AI analysis using the existing ContractRiskEdge
    engine and creates an immutable passport snapshot with all intelligence
    data and cryptographic fingerprints.

    Scoped to the signed-in caller (same pattern as get_read_passport_service
    everywhere else in this router) -- there is no process-wide "the
    passport service" singleton left in this module for a future endpoint to
    reach for by mistake (see the module comment near _configured_repository
    for why that was removed). Note: the real passport-creation path used by
    the app itself is services/version_analysis.py, which already builds its
    own correctly-scoped PassportService per request and never calls this
    HTTP endpoint; nothing in the frontend calls POST /api/passports today,
    so this closes the same class of gap for any future or external caller.
    """
    service = get_create_passport_service(user)
    return await service.create_passport(
        contract_id=body.contract_id,
        contract_version=body.contract_version,
        policy_version=body.policy_version,
        document_content=body.document_content,
        normalized_document=body.normalized_document,
        policy_content=body.policy_content,
    )


@router.get("/{passport_id}", response_model=ContractPassportResponse)
async def get_passport(
    passport_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve a passport by ID."""
    passport = await get_read_passport_service(user).get_passport(passport_id)

    if not passport:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found: {passport_id}"
        )

    return passport


@router.get("/{passport_id}/proof-package")
async def get_proof_package(
    passport_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Download an independently-verifiable proof package for this passport.

    Authorization matches GET /passports/{id}: the signed-in owner (or a
    legacy record with no owner_id). The bundle is meant to be verified later
    with no further LexProof API calls.
    """
    passport = await get_read_passport_service(user).get_passport(passport_id)
    if not passport:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found: {passport_id}",
        )

    passport_doc = passport.model_dump(mode="json")
    evidence_repo = FirestoreRepository("evidence_records")
    live = [
        record
        for record in evidence_repo.stream()
        if record.get("passport_id") == passport_id
    ]
    snapshot_items = list(
        ((passport_doc.get("metadata") or {}).get("verification_snapshot") or {}).get("evidence_items")
        or []
    )
    source = snapshot_items or live
    live_by_id = {
        str(record.get("evidence_id") or record.get("id") or ""): record
        for record in live
    }
    merged: list[dict[str, Any]] = []
    anchors: dict[str, dict[str, Any]] = {}
    for item in source:
        evidence_id = str(item.get("evidence_id") or item.get("id") or "")
        combined = {**item, **(live_by_id.get(evidence_id) or {})}
        merged.append(combined)
        if evidence_id:
            anchor = _evidence_anchor_repository.get(evidence_id)
            if anchor:
                anchors[evidence_id] = anchor

    contract = FirestoreRepository("contracts").get(passport.contract_id) or {}
    return build_proof_package(
        passport_doc,
        evidence_items=merged,
        anchors_by_id=anchors,
        contract_name=contract.get("name") or contract.get("contract_name"),
    )


@contract_router.get("/{contract_id}/passport", response_model=ContractPassportResponse)
async def get_passport_by_contract(
    contract_id: str,
    contract_version: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve a passport by contract and version."""
    passport = await get_read_passport_service(user).get_passport_by_contract(
        contract_id=contract_id,
        contract_version=contract_version,
    )

    if not passport:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found for contract {contract_id}, version {contract_version}"
        )

    return passport


@router.get("", response_model=list[ContractPassportSummary])
async def list_passports(
    contract_id: Optional[str] = Query(None, description="Filter by contract ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of passports"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List passports with optional filtering.

    Uses the signed-in caller's own uid to scope visibility (same tenant
    rule as GET /passports/{id}). Earlier versions of this endpoint used a
    process-wide singleton PassportService that was only armed by a side
    effect of some other request calling analyze_version(), and until that
    happened (e.g. right after a fresh backend restart) fell back to a
    literal tenant_id="read-only" -- which doesn't match any real passport's
    owner_id, so every real passport was silently filtered out and this
    endpoint returned an empty list even for contracts with genuine,
    directly-fetchable passports. That singleton getter has since been
    removed from this module entirely.
    """
    passports = await get_read_passport_service(user).list_passports(
        contract_id=contract_id,
        limit=limit,
        offset=offset,
    )

    return passports


@router.get("/{passport_id}/status")
async def get_passport_status(
    passport_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get passport status."""
    passport = await get_read_passport_service(user).get_passport(passport_id)

    if not passport:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found: {passport_id}"
        )

    return {
        "passport_id": passport.passport_id,
        "status": passport.status,
        "risk_score": passport.risk_score,
        "compliance_score": passport.compliance_score,
        "created_at": passport.created_at,
    }


# ─────────────────────────────────────────────────────────────────────────────────
# Evidence Endpoints
# ─────────────────────────────────────────────────────────────────────────────────

async def get_evidence_service(user: Dict[str, Any] = Depends(get_current_user)) -> EvidenceService:
    """Get EvidenceService instance."""
    return EvidenceService(
        _evidence_service.repository,
        owner_id=str(user["uid"]),
        passport_repository=_evidence_service.passport_repository,
        anchor_repository=_evidence_service.anchor_repository,
        # See the matching comment in get_read_passport_service above: built
        # fresh per request rather than shared off the _evidence_service
        # template, so it stays patchable the same way the other
        # FirestoreRepository(...) calls in this module already are.
        contracts_repository=FirestoreRepository("contracts"),
    )


@router.post("/evidence", response_model=EvidenceItemResponse)
async def create_evidence_item(
    body: EvidenceItemCreate,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Create a new evidence item for a passport."""
    evidence_item = await service.create_evidence_item(
        passport_id=body.passport_id,
        evidence_data=body,
        user=None,
    )

    return evidence_item


@router.get("/evidence/{evidence_id}", response_model=EvidenceItemResponse)
async def get_evidence_item(
    evidence_id: str,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Retrieve an evidence item by ID."""
    evidence_item = await service.get_evidence_item(evidence_id)

    if not evidence_item:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return evidence_item


@router.get("/{passport_id}/evidence", response_model=list[EvidenceItemSummary])
async def get_evidence_by_passport(
    passport_id: UUID,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Retrieve all evidence items for a passport."""
    passport_id_value = str(passport_id)
    if not service.passport_exists(passport_id_value):
        raise HTTPException(status_code=404, detail=f"Passport not found: {passport_id_value}")
    evidence_items = await service.get_evidence_by_passport(passport_id_value)

    return evidence_items


@router.put("/evidence/{evidence_id}", response_model=EvidenceItemResponse)
async def update_evidence_item(
    evidence_id: str,
    body: EvidenceItemUpdate,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Update an evidence item."""
    evidence_item = await service.update_evidence_item(
        evidence_id=evidence_id,
        update_data=body,
    )

    if not evidence_item:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return evidence_item


@router.delete("/evidence/{evidence_id}")
async def delete_evidence_item(
    evidence_id: str,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Delete an evidence item."""
    success = await service.delete_evidence_item(evidence_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return {"message": "Evidence item deleted successfully"}


@router.post("/evidence/{evidence_id}/verify", response_model=EvidenceItemResponse)
async def verify_evidence_item(
    evidence_id: str,
    verification_data: Optional[Dict[str, Any]] = None,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Verify an evidence item."""
    evidence_item = await service.verify_evidence_item(
        evidence_id=evidence_id,
        verification_data=verification_data,
    )

    if not evidence_item:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item not found: {evidence_id}"
        )

    return evidence_item


@router.get("/{passport_id}/evidence/statistics")
async def get_evidence_statistics(
    passport_id: UUID,
    service: EvidenceService = Depends(get_evidence_service),
):
    """Get statistics for evidence items in a passport."""
    passport_id_value = str(passport_id)
    if not service.passport_exists(passport_id_value):
        raise HTTPException(status_code=404, detail=f"Passport not found: {passport_id_value}")
    statistics = await service.get_evidence_statistics(passport_id_value)

    return statistics


async def _load_authorized_passport_and_evidence(
    passport_id_value: str,
    user: Dict[str, Any],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Shared, already-authorized load used by both /verify and /anchor-root.

    Raises HTTPException(404) if the passport doesn't exist or isn't visible
    to the signed-in caller (same org-aware rule as GET /passports/{id}).
    """
    passport_service = get_read_passport_service(user)

    passport_doc: Dict[str, Any] | None = None
    passport_response = await passport_service.get_passport(passport_id_value)
    if passport_response:
        passport_doc = passport_response.model_dump(mode="json")
    else:
        repository = FirestoreRepository("legal_passports")
        stored = repository.get(passport_id_value)
        if stored and stored.get("owner_id") == str(user["uid"]):
            passport_doc = stored

    if not passport_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Passport not found: {passport_id_value}"
        )

    evidence_items = await passport_service.get_evidence(passport_id_value)
    if not evidence_items:
        evidence_service = await get_evidence_service(user)
        if evidence_service.repository is not None:
            # FirestoreRepository.stream() is a synchronous generator over the
            # real (sync) Firestore SDK client -- calling it directly here
            # runs a full evidence_records collection scan on the event
            # loop's own thread, blocking every other concurrent request
            # (including the sibling GET /evidence and GET
            # /evidence/statistics calls this same page load fires) until it
            # finishes. This is the status-and-plan.md §2c hang's most common
            # trigger in practice: passport_service.get_evidence() above only
            # ever reads an in-process dict populated at passport-creation
            # time, so for any passport not created in this exact process's
            # memory (the normal case after a dev-server restart, or with
            # seeded/pre-existing demo data) this fallback runs on every
            # single /verify call, not as a rare edge case. Push the blocking
            # scan onto a worker thread so it can't stall the loop.
            repository = evidence_service.repository
            # Phase 3H.5 (P2 fix): this fallback used to gate on a bare
            # owner_id comparison, so an authorized org member (anyone
            # other than the exact owner_id on the evidence record) was
            # silently denied evidence here even though the normal Evidence
            # read paths (get_evidence_item, get_evidence_by_passport) grant
            # them access via the shared org-aware visibility rule. Reuse
            # that exact same rule -- EvidenceService._is_visible, which
            # wraps .authorization.is_visible_via_contract -- instead of
            # re-implementing a second, inconsistent authorization check
            # here. Legacy/orgless records (no contract_id resolvable, or no
            # contracts_repository) fall through to the same strict
            # owner-only rule as before.
            is_visible = evidence_service._is_visible

            def _scan_evidence_for_passport() -> list[dict[str, Any]]:
                return [
                    record
                    for record in repository.stream()
                    if record.get("passport_id") == passport_id_value
                    and is_visible(record)
                ]

            evidence_items = await asyncio.to_thread(_scan_evidence_for_passport)

    return passport_doc, evidence_items


@router.post("/{passport_id}/verify")
async def verify_passport_integrity_endpoint(
    passport_id: UUID,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Verify passport integrity by recomputing hashes, extended with the
    additive Sepolia passport-root anchor state (see
    docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md §16, §23).

    This endpoint never trusts the frontend hash. It recomputes all
    cryptographic hashes from the persisted data and compares them
    with the stored hash in metadata.passport_hash. It then separately
    reports whether a matching root exists on the additive
    LexProofPassportRegistry contract -- an on-chain "anchor_status" field
    alongside (never instead of) the original document/policy/analysis/
    evidence/passport_hash statuses. A blockchain match can never turn a
    local FAIL or UNVERIFIABLE result into PASS.

    Args:
        passport_id: Passport ID to verify

    Returns:
        Verification result with verified status, component details, and
        the passport-root anchor_status.
    """
    passport_id_value = str(passport_id)
    passport_doc, evidence_items = await _load_authorized_passport_and_evidence(passport_id_value, user)
    integrity = verify_passport_integrity(passport_doc, evidence_items=evidence_items)

    anchor_service = await asyncio.to_thread(
        get_passport_root_anchor_service,
        repository=_passport_anchor_repository,
    )
    return await anchor_service.verify_passport_root_status(passport_id_value, integrity)


@router.post("/{passport_id}/anchor-root")
async def anchor_passport_root_endpoint(
    passport_id: UUID,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Anchor this Legal Passport's ROOT commitment (metadata.passport_hash)
    on the additive LexProofPassportRegistry Sepolia contract.

    SECURITY: the client supplies only the passport_id in the URL -- no
    hashes, scores, or other values are accepted from the request body. The
    server independently loads the passport (through the same org-aware
    authorization as every other /passports/{id} route), recomputes and
    verifies its integrity, and only ever anchors the server-recomputed
    root. A passport is eligible only when every claimed component
    (document/policy/analysis/evidence) AND the stored passport_hash binding
    are PASS; UNVERIFIABLE (legacy / evidence-only snapshots) and FAIL are
    both refused. This call is idempotent: re-anchoring an already-anchored
    passport returns the existing anchor without a new transaction, and a
    passport that already has a DIFFERENT anchored root is refused outright
    (a root, once anchored, is never overwritten).

    This is a NEW, dedicated endpoint -- it does not reuse and is not
    reachable through the legacy, unsafe `POST /passports/{id}/anchor`
    route (see api/blockchain.py), which accepted client-supplied hashes
    and called the unrelated `registerProof` primitive.
    """
    passport_id_value = str(passport_id)
    passport_doc, evidence_items = await _load_authorized_passport_and_evidence(passport_id_value, user)
    integrity = verify_passport_integrity(passport_doc, evidence_items=evidence_items)

    anchor_service = await asyncio.to_thread(
        get_passport_root_anchor_service,
        repository=_passport_anchor_repository,
    )

    try:
        return await anchor_service.anchor_passport_root(
            passport_id_value,
            passport_doc,
            integrity,
            actor_id=str(user.get("uid") or "system"),
            org_id=passport_doc.get("org_id"),
        )
    except PassportEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "reasons": exc.reasons,
            },
        ) from exc
    except PassportRootConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        if "not configured" in message.lower():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Passport root anchoring is temporarily unavailable: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surfaced as a 500 like every other route here
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error anchoring passport root to Ethereum: {exc}",
        ) from exc
