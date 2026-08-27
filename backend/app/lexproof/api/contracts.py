"""Authenticated contract upload and analysis endpoints."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ..services.auth import get_current_user
from ..config import get_settings
from ..domains.passport.service import PassportService
from ..domains.passport.api.router import configure_passport_service
from ..repositories.cloud_storage import CloudStorageRepository
from ..repositories.firestore import FirestoreRepository
from ..services.vertex_ai import VertexGeminiProvider, VertexAIError

router = APIRouter(prefix="/contracts", tags=["contracts"])
logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_TYPES = {"text/plain", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}


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
    existing_contract_versions = {
        (record["contract_id"], record["version"])
        for record in records
        if record.get("contract_id") and record.get("version") is not None
    }

    # Early imports persisted the analysis output directly as passports rather
    # than creating a separate contracts/contract_versions document. Surface
    # those real records too, so their evidence remains reachable in the UI.
    for passport in passports.stream():
        if not _is_visible_to_user(passport, uid):
            continue
        identity = (passport.get("contract_id"), passport.get("contract_version"))
        if not identity[0] or identity in existing_contract_versions:
            continue
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


def parse_structured_analysis(content: str) -> dict[str, Any]:
    """Parse Gemini JSON output without manufacturing missing analysis data."""
    candidates = [content.strip()]
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content.strip(), re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if not isinstance(parsed.get("findings"), list):
                raise ValueError("Vertex AI response omitted findings")
            return parsed

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", content):
        try:
            parsed, _ = decoder.raw_decode(content[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if not isinstance(parsed.get("findings"), list):
                raise ValueError("Vertex AI response omitted findings")
            return parsed
    raise ValueError("Vertex AI returned invalid structured analysis")


def _log_analysis_parse_failure(content: str) -> None:
    preview = " ".join(content[:500].split())
    logger.warning("Vertex AI structured analysis parse failed (length=%d, preview=%r)", len(content), preview)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_contract(file: UploadFile = File(...), user: dict[str, Any] = Depends(get_current_user)):
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
    contract_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(content).hexdigest()
    storage_path = f"contracts/{uid}/{contract_id}/{version_id}/original/{filename}"
    contracts, versions, storage = _repositories()
    try:
        storage_uri = storage.upload(storage_path, content, file.content_type)
        contracts.set(contract_id, {"id": contract_id, "owner_id": uid, "name": filename, "status": "uploaded", "current_version_id": version_id, "created_at": now, "updated_at": now})
        versions.set(version_id, {"id": version_id, "owner_id": uid, "contract_id": contract_id, "version_number": 1, "storage_path": storage_uri, "content_hash": content_hash, "created_at": now, "analysis_status": "pending", "filename": filename, "content_type": file.content_type, "document_text": _extract_text(filename, content)})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Contract persistence failed: {exc}") from exc
    return {"contract_id": contract_id, "version_id": version_id, "content_hash": content_hash, "status": "uploaded"}


@router.post("/{contract_id}/analyze")
async def analyze_contract(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    contract = contracts.get(contract_id)
    if not contract or contract.get("owner_id") != uid:
        raise HTTPException(status_code=404, detail="Contract not found")
    version = versions.get(contract["current_version_id"])
    if not version or version.get("owner_id") != uid:
        raise HTTPException(status_code=404, detail="Contract version not found")
    provider = VertexGeminiProvider()

    class Request:
        prompt = (
            "Return JSON only with risk_score (0-100), compliance_score (0-100), risk_level, findings[], "
            "key_clauses[], and compliance_items[]. Each finding must contain: title, severity, description, "
            "evidence, recommendation, risk_impact (0-100), compliance_impact (0-100), source_section, and evidence_quote. "
            "For source_section, cite the exact clause, section, or page reference (e.g., 'Section 7.2', 'Clause 12.3', 'Page 5'). "
            "For evidence_quote, extract the exact text from the contract that supports this finding. "
            "Do not omit fields. Use 0 when a finding truly has zero impact; never invent missing values or contract text.\n\nContract:\n"
            + version["document_text"]
        )
        model = None
        system_prompt = "You are a legal contract risk analyst. Analyze only the supplied contract."

    try:
        response = await provider.complete(Request())
        try:
            analysis = parse_structured_analysis(response.content)
        except ValueError:
            _log_analysis_parse_failure(response.content)
            raise
    except VertexAIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Vertex AI returned invalid structured analysis") from exc
    findings = analysis["findings"]

    async def engine(document: str, policy: str) -> dict[str, Any]:
        return analysis

    passport_service = PassportService(engine, user_id=uid, tenant_id=uid, repository=FirestoreRepository("legal_passports"))
    passport = await passport_service.create_passport(
        contract_id=contract_id, contract_version=version["version_number"], policy_version="default", document_content=version["document_text"], metadata={"owner_id": uid, "risk_level": analysis.get("risk_level"), "key_clauses": analysis.get("key_clauses", []), "compliance_items": analysis.get("compliance_items", []), "content_hash": version["content_hash"]}
    )
    now = datetime.now(timezone.utc).isoformat()
    FirestoreRepository("legal_passports").set(passport.passport_id, {**passport.model_dump(mode="json"), "id": passport.passport_id, "owner_id": uid, "version_id": version["id"], "risk_level": analysis.get("risk_level"), "findings_count": len(findings), "content_hash": version["content_hash"], "blockchain_status": "not_anchored", "analysis_timestamp": now})
    for finding in findings:
        finding_id = str(uuid.uuid4())
        FirestoreRepository("risk_findings").set(finding_id, {"id": finding_id, "owner_id": uid, "contract_id": contract_id, "version_id": version["id"], **finding, "created_at": now})
    evidence_repository = FirestoreRepository("evidence_records")
    for evidence_item in await passport_service.get_evidence(passport.passport_id):
        evidence_repository.set(evidence_item["evidence_id"], evidence_item)
    versions.set(version["id"], {"analysis_status": "complete", "passport_id": passport.passport_id}, merge=True)
    configure_passport_service(passport_service)
    return passport
