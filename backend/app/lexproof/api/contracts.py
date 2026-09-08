"""Authenticated contract upload and analysis endpoints."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..services.auth import get_current_user, load_org_member
from ..config import get_settings
from ..domains.passport.api.router import configure_passport_service
from ..repositories.cloud_storage import CloudStorageRepository
from ..repositories.firestore import FirestoreRepository
from ..repositories.firestore import EvidenceAnchorRepository
from ..services.vertex_ai import VertexGeminiProvider
from ..services.ethereum_anchor_service import get_ethereum_anchor_service
from ..services.version_analysis import VersionAnalysisService, parse_structured_analysis
from ..services.audit import record_audit_event
from ..services.contract_versions import (
    ContractNotFoundError,
    SourceVersionNotFoundError,
    create_contract_version,
)

router = APIRouter(prefix="/contracts", tags=["contracts"])
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_TYPES = {"text/plain", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}


class ContractVersionCreateRequest(BaseModel):
    source_version_id: str
    storage_path: str | None = None
    content_hash: str | None = None
    filename: str | None = None
    content_type: str | None = None
    document_text: str | None = None


def _extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _extract_text(filename: str, content: bytes) -> str:
    extension = _extension(filename)
    if extension == ".txt":
        return content.decode("utf-8")
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
            import io
            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="PDF extraction requires pypdf") from exc
    try:
        from docx import Document
        import io
        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="DOCX extraction requires python-docx") from exc


def _repositories() -> tuple[FirestoreRepository, FirestoreRepository, CloudStorageRepository]:
    return FirestoreRepository("contracts"), FirestoreRepository("contract_versions"), CloudStorageRepository()


def _is_visible_to_user(record: dict[str, Any], uid: str) -> bool:
    """Allow the current tenant and legacy records created before owner scoping."""
    owner_id = record.get("owner_id")
    return not owner_id or owner_id == uid


def _passport_contract_name(passport: dict[str, Any]) -> str:
    metadata = passport.get("metadata") or {}
    return metadata.get("contract_name") or metadata.get("contract_title") or passport["contract_id"]


def _contract_summary(
    contract: dict[str, Any],
    versions: FirestoreRepository,
    passports: FirestoreRepository,
    passport: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the current, owner-scoped contract record used by the dashboard."""
    version_id = contract.get("current_version_id")
    version = versions.get(version_id) if version_id else None
    passport_id = (version.get("passport_id") if version else None) or (passport or {}).get("passport_id") or (passport or {}).get("id")
    passport = passport or (passports.get(passport_id) if passport_id else None)

    return {
        "contract_id": contract.get("id") or contract.get("contract_id") or (passport or {}).get("contract_id"),
        "name": contract.get("name") or contract.get("contract_name") or (_passport_contract_name(passport) if passport else None),
        "status": contract.get("status"),
        "created_at": contract.get("created_at"),
        "updated_at": contract.get("updated_at"),
        "version": (version.get("version_number") if version else None) or (passport or {}).get("contract_version"),
        "analysis_status": version.get("analysis_status") if version else None,
        "passport_id": passport_id,
        "risk_score": passport.get("risk_score") if passport else None,
        "risk_level": passport.get("risk_level") if passport else None,
        "evidence_count": passport.get("evidence_count") if passport else None,
    }


@router.get("")
async def list_contracts(user: dict[str, Any] = Depends(get_current_user)):
    """List the signed-in user's contracts with their current passport summary."""
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    passports = FirestoreRepository("legal_passports")
    records = [
        _contract_summary(contract, versions, passports)
        for contract in contracts.stream()
        if _is_visible_to_user(contract, uid)
    ]
    # A contract with a real contracts/ document is fully represented by its
    # one row above (showing its current version) regardless of how many
    # older passport versions exist for it, so only the contract_id matters
    # here -- keying this on (contract_id, version) previously let every
    # non-current passport version of an otherwise normal contract slip past
    # this de-dup check and get treated as a phantom "legacy" row below,
    # producing duplicate rows for the same contract in the list.
    existing_contract_ids = {
        record["contract_id"]
        for record in records
        if record.get("contract_id")
    }

    # Early imports persisted the analysis output directly as passports rather
    # than creating a separate contracts/contract_versions document. Surface
    # those real records too, so their evidence remains reachable in the UI.
    # This must only fire for passports with no contracts/ document at all
    # (true legacy/orphan imports) -- not for older versions of a contract
    # that does have one, which already have all their versions covered by
    # the current-version row built above.
    latest_orphan_passport_by_contract: dict[str, dict[str, Any]] = {}
    for passport in passports.stream():
        if not _is_visible_to_user(passport, uid):
            continue
        contract_id = passport.get("contract_id")
        if not contract_id or contract_id in existing_contract_ids:
            continue
        current = latest_orphan_passport_by_contract.get(contract_id)
        if current is None or (passport.get("contract_version") or 0) > (current.get("contract_version") or 0):
            latest_orphan_passport_by_contract[contract_id] = passport
    for passport in latest_orphan_passport_by_contract.values():
        records.append(_contract_summary({}, versions, passports, passport=passport))
    return sorted(records, key=lambda record: record.get("updated_at") or "", reverse=True)


@router.get("/{contract_id}")
async def get_contract(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    """Get one signed-in user's contract and current passport summary."""
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    contract = contracts.get(contract_id)
    passports = FirestoreRepository("legal_passports")
    if contract and _is_visible_to_user(contract, uid):
        return _contract_summary(contract, versions, passports)

    legacy_passports = [
        passport
        for passport in passports.stream()
        if passport.get("contract_id") == contract_id and _is_visible_to_user(passport, uid)
    ]
    if not legacy_passports:
        raise HTTPException(status_code=404, detail="Contract not found")
    latest_passport = max(legacy_passports, key=lambda passport: passport.get("contract_version", 0))
    return _contract_summary({}, versions, passports, passport=latest_passport)


@router.get("/{contract_id}/versions")
async def list_contract_versions(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    """Return the read-only version history for an owned contract."""
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    contract = contracts.get(contract_id)
    if not contract or contract.get("owner_id") != uid:
        raise HTTPException(status_code=404, detail="Contract not found")

    passports = FirestoreRepository("legal_passports")
    proposals = FirestoreRepository("redline_proposals")
    published_versions = {
        proposal.get("published_version_id")
        for proposal in proposals.stream()
        if proposal.get("contract_id") == contract_id
    }
    result = []
    for version in versions.stream():
        if version.get("contract_id") != contract_id or not _is_visible_to_user(version, uid):
            continue
        passport_id = version.get("passport_id")
        passport = passports.get(passport_id) if passport_id else None
        result.append({
            "version_id": version.get("id"),
            "version_number": version.get("version_number"),
            "parent_version_id": version.get("parent_version_id"),
            "created_at": version.get("created_at"),
            "created_by": version.get("created_by"),
            "analysis_status": version.get("analysis_status"),
            "passport_id": passport_id,
            "passport_status": passport.get("status") if passport else None,
            "published": version.get("id") in published_versions,
            "is_current": version.get("id") == contract.get("current_version_id"),
        })
    return sorted(result, key=lambda item: item.get("version_number") or 0)


@router.post("/{contract_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_version(
    contract_id: str,
    request: ContractVersionCreateRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Create a new owner-authorized contract version from an existing version."""
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    contract = contracts.get(contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if contract.get("owner_id") != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to create a version")
    try:
        return create_contract_version(
            contract_id,
            request.source_version_id,
            request.model_dump(exclude={"source_version_id"}, exclude_none=True),
            uid,
            contracts=contracts,
            versions=versions,
        )
    except ContractNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found") from exc
    except SourceVersionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source contract version not found") from exc


def _version_analysis_service(
    contracts: FirestoreRepository,
    versions: FirestoreRepository,
) -> VersionAnalysisService:
    return VersionAnalysisService(
        contracts=contracts,
        versions=versions,
        repository_factory=FirestoreRepository,
        anchor_repository_factory=EvidenceAnchorRepository,
        provider_factory=VertexGeminiProvider,
        anchor_service_factory=get_ethereum_anchor_service,
        passport_configurator=configure_passport_service,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_contract(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
):
    filename = file.filename or ""
    extension = _extension(filename)
    if not filename or filename != filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only PDF, DOCX, and TXT files are allowed")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported contract content type")
    content = await file.read(MAX_FILE_SIZE + 1)
    if not content or len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Contract file must be between 1 byte and 10 MB")
    uid = str(user["uid"])
    org_id = load_org_member(x_org_id.strip(), user)["org_id"] if x_org_id and x_org_id.strip() else None
    contract_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(content).hexdigest()
    storage_path = f"contracts/{uid}/{contract_id}/{version_id}/original/{filename}"
    contracts, versions, storage = _repositories()
    try:
        storage_uri = storage.upload(storage_path, content, file.content_type)
        contract_record = {"id": contract_id, "owner_id": uid, "name": filename, "status": "uploaded", "current_version_id": version_id, "created_at": now, "updated_at": now}
        version_record = {"id": version_id, "owner_id": uid, "contract_id": contract_id, "version_number": 1, "storage_path": storage_uri, "content_hash": content_hash, "created_at": now, "analysis_status": "pending", "filename": filename, "content_type": file.content_type, "document_text": _extract_text(filename, content)}
        if org_id:
            contract_record["org_id"] = org_id
            version_record["org_id"] = org_id
        contracts.set(contract_id, contract_record)
        versions.set(version_id, version_record)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Contract persistence failed: {exc}") from exc
    record_audit_event(
        actor_id=uid,
        actor_email=user.get("email"),
        action="contract.uploaded",
        resource_type="contract",
        resource_id=contract_id,
        resource_name=filename,
        summary=f"Uploaded contract \"{filename}\"",
        org_id=org_id,
    )
    return {"contract_id": contract_id, "version_id": version_id, "content_hash": content_hash, "status": "uploaded"}


@router.post("/{contract_id}/analyze")
async def analyze_contract(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    contract = contracts.get(contract_id)
    if not contract or contract.get("owner_id") != uid:
        raise HTTPException(status_code=404, detail="Contract not found")
    result = await _version_analysis_service(contracts, versions).analyze_version(
        contract_id,
        contract["current_version_id"],
        uid,
        anchor_evidence=False,
    )
    return result["passport"]


@router.post("/{contract_id}/versions/{version_id}/analyze")
async def analyze_explicit_version(contract_id: str, version_id: str, user: dict[str, Any] = Depends(get_current_user)):
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    result = await _version_analysis_service(contracts, versions).analyze_version(
        contract_id,
        version_id,
        uid,
        anchor_evidence=True,
    )
    return {
        "contract_id": contract_id,
        "version_id": version_id,
        "version_number": versions.get(version_id)["version_number"],
        "passport_id": result["passport_id"],
        "analysis_status": result["analysis_status"],
        "finding_count": result["finding_count"],
        "evidence_count": result["evidence_count"],
    }
