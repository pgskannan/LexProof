"""Authenticated contract upload and analysis endpoints."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..services.auth import get_current_user, load_org_member
from ..services.organizations import contract_owner_or_org_admin, get_organization_service
from ..config import get_settings
from ..domains.passport.api.router import configure_passport_service
from ..repositories.cloud_storage import CloudStorageRepository
from ..repositories.firestore import FirestoreRepository
from ..repositories.firestore import EvidenceAnchorRepository
from ..services.vertex_ai import VertexAIError, VertexGeminiProvider
from ..services.ethereum_anchor_service import get_ethereum_anchor_service
from ..services.version_analysis import VersionAnalysisService, parse_structured_analysis
from ..services.audit import record_audit_event
from ..services.contract_versions import (
    ContractNotFoundError,
    SourceVersionNotFoundError,
    create_contract_version,
)
from ..services.pii import detect_pii
from ..services.executive_summary import ExecutiveSummaryError, get_executive_summary_service
from ..services.published_version_status import project_published_version_status, project_published_version_status_batch

router = APIRouter(prefix="/contracts", tags=["contracts"])
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_TYPES = {
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/tiff",
}
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
# Below this many extracted characters per PDF page, treat the PDF as scanned
# (image-only) and fall back to OCR rather than trusting pypdf's near-empty text.
OCR_MIN_CHARS_PER_PAGE = 20


class ContractVersionCreateRequest(BaseModel):
    source_version_id: str
    storage_path: str | None = None
    content_hash: str | None = None
    filename: str | None = None
    content_type: str | None = None
    document_text: str | None = None


def _extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _configure_tesseract_cmd(pytesseract_module) -> None:
    """Point pytesseract at an explicit binary path when PATH lookup won't work.

    Some hosts (notably a stock Windows install via winget) never add
    Tesseract-OCR to PATH, so the plain "tesseract" lookup pytesseract does by
    default fails even though the binary is genuinely installed. Settings.
    tesseract_cmd (env TESSERACT_CMD) lets an operator point at it directly,
    e.g. "C:\\Program Files\\Tesseract-OCR\\tesseract.exe". Left unset, this
    is a no-op and pytesseract's normal PATH-based lookup is used unchanged.
    """
    configured_path = get_settings().tesseract_cmd
    if configured_path:
        pytesseract_module.pytesseract.tesseract_cmd = configured_path


def _ocr_engine_available() -> bool:
    """Whether the Tesseract OCR binary is actually installed on this host.

    pytesseract is a pure-Python wrapper; it imports fine even when the
    underlying `tesseract` binary is missing, so this must probe the binary
    itself rather than just the import.
    """
    try:
        import pytesseract
        _configure_tesseract_cmd(pytesseract)
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


_OCR_PENDING_NOTICE = (
    "[OCR pending: this document was uploaded successfully, but no embedded text "
    "could be found and the Tesseract OCR engine is not installed on this server, "
    "so text could not be extracted yet. Install Tesseract "
    "(https://github.com/tesseract-ocr/tesseract) on the server and re-run analysis "
    "to extract and analyze this document's text.]"
)


def _ocr_image_bytes(content: bytes) -> str:
    import io

    import pytesseract
    from PIL import Image

    _configure_tesseract_cmd(pytesseract)
    return pytesseract.image_to_string(Image.open(io.BytesIO(content)))


def _ocr_pdf_bytes(content: bytes) -> str:
    import io

    import pymupdf
    import pytesseract
    from PIL import Image

    _configure_tesseract_cmd(pytesseract)
    pages_text: list[str] = []
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            pixmap = page.get_pixmap(dpi=200)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            pages_text.append(pytesseract.image_to_string(image))
    return "\n".join(pages_text)


def _extract_text(filename: str, content: bytes) -> tuple[str, str]:
    """Extract document text for analysis.

    Returns (document_text, ocr_status). ocr_status is one of:
    - "not_applicable": plain text/DOCX, no OCR involved.
    - "native_text": PDF had embedded text; no OCR needed.
    - "ocr_success": OCR ran (image, or scanned PDF) and produced text.
    - "ocr_unavailable": OCR was needed but the Tesseract binary is not
      installed on this server; document_text holds whatever text is
      available (native PDF text if any, otherwise a placeholder notice).
    """
    extension = _extension(filename)
    if extension == ".txt":
        return content.decode("utf-8", errors="replace"), "not_applicable"

    if extension in IMAGE_EXTENSIONS:
        # Never block the upload on missing OCR dependencies (Pillow/pytesseract
        # not installed, or the Tesseract binary missing) -- persist the file
        # with a clear pending-OCR status so it can be re-analyzed once OCR is
        # configured, matching the PDF scanned-document fallback below.
        if not _ocr_engine_available():
            return _OCR_PENDING_NOTICE, "ocr_unavailable"
        try:
            text = _ocr_image_bytes(content)
        except Exception:
            return _OCR_PENDING_NOTICE, "ocr_unavailable"
        return (text, "ocr_success") if text.strip() else (_OCR_PENDING_NOTICE, "ocr_unavailable")

    if extension == ".pdf":
        try:
            from pypdf import PdfReader
            import io
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="PDF extraction requires pypdf") from exc
        try:
            page_texts = [page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages]
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not read PDF: {exc}") from exc
        native_text = "\n".join(page_texts)
        page_count = max(len(page_texts), 1)
        if len(native_text.strip()) >= OCR_MIN_CHARS_PER_PAGE * page_count:
            return native_text, "native_text"

        # Little or no embedded text -- likely a scanned PDF. Fall back to OCR.
        try:
            import pymupdf  # noqa: F401
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            return (native_text or _OCR_PENDING_NOTICE), "ocr_unavailable" if not native_text.strip() else "native_text"
        if not _ocr_engine_available():
            return (native_text or _OCR_PENDING_NOTICE), "ocr_unavailable"
        try:
            ocr_text = _ocr_pdf_bytes(content)
        except Exception:
            return (native_text or _OCR_PENDING_NOTICE), "native_text" if native_text.strip() else "ocr_unavailable"
        return (ocr_text.strip() or native_text or _OCR_PENDING_NOTICE), "ocr_success" if ocr_text.strip() else "ocr_unavailable"

    try:
        from docx import Document
        import io
        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs), "not_applicable"
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="DOCX extraction requires python-docx") from exc


def _repositories() -> tuple[FirestoreRepository, FirestoreRepository, CloudStorageRepository]:
    return FirestoreRepository("contracts"), FirestoreRepository("contract_versions"), CloudStorageRepository()


def _is_visible_to_user(
    record: dict[str, Any],
    uid: str,
    *,
    organization_id: str | None = None,
    member_by_org: dict[str, Any] | None = None,
) -> bool:
    """Use organization membership for org-owned records and owner fallback for legacy data."""
    record_org_id = record.get("org_id") or organization_id
    if record_org_id:
        org_id = str(record_org_id)
        if member_by_org is not None:
            return bool(member_by_org.get(org_id))
        return bool(get_organization_service().get_active_member(org_id, uid))
    owner_id = record.get("owner_id")
    return not owner_id or owner_id == uid


def _member_lookup(records: list[dict[str, Any]], uid: str) -> dict[str, Any]:
    """Resolve get_active_member once per org instead of once per list row."""
    org_ids = {str(record["org_id"]) for record in records if record.get("org_id")}
    orgs = get_organization_service()
    return {org_id: orgs.get_active_member(org_id, uid) for org_id in org_ids}


def _passport_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in records:
        if item.get("id"):
            indexed[str(item["id"])] = item
        if item.get("passport_id"):
            indexed[str(item["passport_id"])] = item
    return indexed


def _passport_contract_name(passport: dict[str, Any]) -> str:
    metadata = passport.get("metadata") or {}
    return metadata.get("contract_name") or metadata.get("contract_title") or passport["contract_id"]


def _contract_summary(
    contract: dict[str, Any],
    versions: FirestoreRepository,
    passports: FirestoreRepository,
    passport: dict[str, Any] | None = None,
    status_projection: dict[str, Any] | None = None,
    version_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the current, owner-scoped contract record used by the dashboard."""
    version_id = contract.get("current_version_id")
    version = version_record if version_record is not None else versions.get(version_id) if version_id else None
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
        **(status_projection or {}),
    }


@router.get("")
async def list_contracts(
    user: dict[str, Any] = Depends(get_current_user),
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
):
    """List the signed-in user's contracts with their current passport summary.

    The findings contract picker and dashboard both call this on first paint.
    Streaming every contracts/versions/passports/proposals document made the
    picker sit on "No contracts match" long enough that the golden-path E2E
    timed out waiting for demo-golden-path-master-services-agreement. When
    the client sends X-Org-Id (OrgProvider always does after login), query
    that org and get_many the current versions instead of scanning the
    whole workspace.
    """
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    passports = FirestoreRepository("legal_passports")
    proposals = FirestoreRepository("redline_proposals")
    evidence_records = FirestoreRepository("evidence_records")
    evidence_anchors = EvidenceAnchorRepository("evidence_anchors")
    findings = FirestoreRepository("risk_findings")
    org_id = (x_org_id or "").strip() or None
    if org_id:
        if not get_organization_service().get_active_member(org_id, uid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not an active member of this organization",
            )
        contract_records = contracts.query(equal={"org_id": org_id})
        passport_records = passports.query(equal={"org_id": org_id})
        proposal_records = proposals.query(equal={"org_id": org_id})
        member_by_org = {org_id: True}
    else:
        streamed_contracts = list(contracts.stream())
        member_by_org = _member_lookup(streamed_contracts, uid)
        contract_records = [
            contract
            for contract in streamed_contracts
            if _is_visible_to_user(contract, uid, member_by_org=member_by_org)
        ]
        passport_records = list(passports.stream())
        proposal_records = list(proposals.stream())
    version_ids = [
        contract.get("current_version_id")
        for contract in contract_records
        if contract.get("current_version_id")
    ]
    version_by_id = versions.get_many(version_ids) if version_ids else {}
    version_records = list(version_by_id.values())
    passport_by_id = _passport_index(passport_records)
    missing_passport_ids = [
        version.get("passport_id")
        for version in version_records
        if version.get("passport_id") and str(version.get("passport_id")) not in passport_by_id
    ]
    if missing_passport_ids:
        passport_records = [*passport_records, *passports.get_many(missing_passport_ids).values()]
        passport_by_id = _passport_index(passport_records)
    published_version_ids = {
        item.get("published_version_id")
        for item in proposal_records
        if item.get("published_version_id") in version_by_id
    }
    if org_id and published_version_ids:
        # The org-scoped passport query only returns passports that carry an
        # org_id. Passports written for a published redline version by older
        # analysis runs may not, and the full-scan path would still find them
        # by version_id or (contract_id, version_number). Without this, the
        # same contract showed "Failed — retry" in the list (no passport, no
        # evidence) while its own detail page showed Confirmed.
        linked_version_ids = {
            item.get("version_id") for item in passport_records if item.get("version_id")
        }
        linked_contract_versions = {
            (item.get("contract_id"), item.get("contract_version")) for item in passport_records
        }
        unresolved_contract_ids = {
            version.get("contract_id")
            for version_id, version in version_by_id.items()
            if version_id in published_version_ids
            and not version.get("passport_id")
            and version_id not in linked_version_ids
            and (version.get("contract_id"), version.get("version_number")) not in linked_contract_versions
            and version.get("contract_id")
        }
        known_passport_ids = set(passport_by_id)
        for contract_id in sorted(unresolved_contract_ids):
            for item in passports.query(equal={"contract_id": contract_id}):
                # The contract itself was already scoped to this org above.
                if item.get("org_id") in (None, org_id):
                    key = str(item.get("passport_id") or item.get("id"))
                    if key not in known_passport_ids:
                        passport_records.append(item)
                        known_passport_ids.add(key)
        passport_by_id = _passport_index(passport_records)
    evidence_record_snapshot = list(evidence_records.stream()) if published_version_ids else []
    evidence_anchor_snapshot = list(evidence_anchors.stream()) if published_version_ids else []
    finding_snapshot = list(findings.stream()) if published_version_ids else []
    status_by_version = project_published_version_status_batch(
        version_records,
        proposal_records,
        passport_records,
        evidence_record_snapshot,
        evidence_anchor_snapshot,
        finding_snapshot,
    )
    records = [
        _contract_summary(
            contract,
            versions,
            passports,
            passport=passport_by_id.get((version_by_id.get(contract.get("current_version_id")) or {}).get("passport_id")),
            status_projection=status_by_version.get(contract.get("current_version_id")),
            version_record=version_by_id.get(contract.get("current_version_id")),
        )
        for contract in contract_records
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
    for passport in passport_records:
        if not _is_visible_to_user(passport, uid, member_by_org=member_by_org):
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
    if contract is not None and not _is_visible_to_user(contract, uid):
        # Same 404 as a missing contract. Do not fall through to a full
        # legal_passports stream: that scan turned cross-tenant denials into
        # 500s under real Firestore load (cross-tenant isolation E2E).
        raise HTTPException(status_code=404, detail="Contract not found")

    passports = FirestoreRepository("legal_passports")
    if contract is not None:
        proposals = FirestoreRepository("redline_proposals")
        evidence_records = FirestoreRepository("evidence_records")
        evidence_anchors = EvidenceAnchorRepository("evidence_anchors")
        findings = FirestoreRepository("risk_findings")
        current_version = versions.get(contract.get("current_version_id")) if contract.get("current_version_id") else None
        return _contract_summary(
            contract,
            versions,
            passports,
            status_projection=project_published_version_status(
                current_version,
                next((item for item in proposals.stream() if item.get("published_version_id") == (current_version or {}).get("id")), None),
                passports=passports,
                evidence_records=evidence_records,
                evidence_anchors=evidence_anchors,
                findings=findings,
            ) if current_version else None,
        )

    legacy_passports = [
        passport
        for passport in passports.query(equal={"contract_id": contract_id})
        if _is_visible_to_user(passport, uid)
    ]
    if not legacy_passports:
        raise HTTPException(status_code=404, detail="Contract not found")
    latest_passport = max(legacy_passports, key=lambda passport: passport.get("contract_version", 0))
    return _contract_summary({}, versions, passports, passport=latest_passport)


@router.get("/{contract_id}/versions")
async def list_contract_versions(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    """Return the read-only version history for an accessible contract."""
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    contract = contracts.get(contract_id)
    if not contract or not _is_visible_to_user(contract, uid):
        raise HTTPException(status_code=404, detail="Contract not found")

    passports = FirestoreRepository("legal_passports")
    proposals = FirestoreRepository("redline_proposals")
    evidence_records = FirestoreRepository("evidence_records")
    evidence_anchors = EvidenceAnchorRepository("evidence_anchors")
    findings = FirestoreRepository("risk_findings")
    published_versions = {
        proposal.get("published_version_id")
        for proposal in proposals.stream()
        if proposal.get("contract_id") == contract_id
    }
    result = []
    for version in versions.stream():
        if version.get("contract_id") != contract_id or not _is_visible_to_user(
            version,
            uid,
            organization_id=contract.get("org_id"),
        ):
            continue
        passport_id = version.get("passport_id")
        passport = passports.get(passport_id) if passport_id else None
        status_projection = project_published_version_status(
            version,
            next((item for item in proposals.stream() if item.get("published_version_id") == version.get("id")), None),
            passports=passports,
            evidence_records=evidence_records,
            evidence_anchors=evidence_anchors,
            findings=findings,
        )
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
            "ocr_status": version.get("ocr_status"),
            "pii_types": version.get("pii_types") or [],
            "contains_pii": bool(version.get("contains_pii")),
            **status_projection,
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
    if not contract_owner_or_org_admin(contract, uid):
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


MAX_BULK_FILES = 20


def _validate_upload(filename: str, content_type: str | None) -> None:
    extension = _extension(filename)
    if not filename or filename != filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only PDF, DOCX, TXT, JPG, PNG, and TIFF files are allowed")
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported contract content type")


def _persist_upload(
    filename: str,
    content: bytes,
    content_type: str,
    uid: str,
    org_id: str | None,
    contracts: FirestoreRepository,
    versions: FirestoreRepository,
    storage: CloudStorageRepository,
    *,
    actor_email: str | None = None,
) -> dict[str, Any]:
    """Shared upload-persistence logic behind both the single-file and bulk-upload endpoints."""
    contract_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(content).hexdigest()
    storage_path = f"contracts/{uid}/{contract_id}/{version_id}/original/{filename}"
    try:
        storage_uri = storage.upload(storage_path, content, content_type)
        contract_record = {"id": contract_id, "owner_id": uid, "name": filename, "status": "uploaded", "current_version_id": version_id, "created_at": now, "updated_at": now}
        document_text, ocr_status = _extract_text(filename, content)
        pii_types = detect_pii(document_text)
        version_record = {"id": version_id, "owner_id": uid, "contract_id": contract_id, "version_number": 1, "storage_path": storage_uri, "content_hash": content_hash, "created_at": now, "analysis_status": "pending", "filename": filename, "content_type": content_type, "document_text": document_text, "ocr_status": ocr_status, "pii_types": pii_types, "contains_pii": bool(pii_types)}
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
        actor_email=actor_email,
        action="contract.uploaded",
        resource_type="contract",
        resource_id=contract_id,
        resource_name=filename,
        contract_id=contract_id,
        summary=f"Uploaded contract \"{filename}\"",
        org_id=org_id,
    )
    return {"contract_id": contract_id, "version_id": version_id, "content_hash": content_hash, "status": "uploaded", "ocr_status": ocr_status}


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_contract(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
):
    filename = file.filename or ""
    _validate_upload(filename, file.content_type)
    content = await file.read(MAX_FILE_SIZE + 1)
    if not content or len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Contract file must be between 1 byte and 10 MB")
    uid = str(user["uid"])
    org_id = load_org_member(x_org_id.strip(), user)["org_id"] if x_org_id and x_org_id.strip() else None
    contracts, versions, storage = _repositories()
    return _persist_upload(filename, content, file.content_type, uid, org_id, contracts, versions, storage, actor_email=user.get("email"))


@router.post("/bulk", status_code=status.HTTP_207_MULTI_STATUS)
async def upload_contracts_bulk(
    files: list[UploadFile] = File(...),
    user: dict[str, Any] = Depends(get_current_user),
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
):
    """Upload several contracts in one request. Every file is attempted independently --

    one bad file (wrong type, too large, corrupt) never blocks the others; each file's
    outcome is reported in `results`, in the same order the files were submitted.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(status_code=413, detail=f"Bulk upload is limited to {MAX_BULK_FILES} files at a time")
    uid = str(user["uid"])
    org_id = load_org_member(x_org_id.strip(), user)["org_id"] if x_org_id and x_org_id.strip() else None
    contracts, versions, storage = _repositories()
    results: list[dict[str, Any]] = []
    for file in files:
        filename = file.filename or ""
        entry: dict[str, Any] = {"filename": filename}
        try:
            _validate_upload(filename, file.content_type)
            content = await file.read(MAX_FILE_SIZE + 1)
            if not content or len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="Contract file must be between 1 byte and 10 MB")
            persisted = _persist_upload(filename, content, file.content_type, uid, org_id, contracts, versions, storage, actor_email=user.get("email"))
            entry.update(persisted)
            entry["ok"] = True
        except HTTPException as exc:
            entry["ok"] = False
            entry["detail"] = exc.detail
        except Exception as exc:  # noqa: BLE001 -- one file's unexpected failure must never abort the batch
            entry["ok"] = False
            entry["detail"] = f"Upload failed: {exc}"
        results.append(entry)
    return {"results": results}


@router.post("/{contract_id}/analyze")
async def analyze_contract(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    uid = str(user["uid"])
    contracts, versions, _ = _repositories()
    contract = contracts.get(contract_id)
    if not contract or not contract_owner_or_org_admin(contract, uid):
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


@router.get("/{contract_id}/executive-summary")
async def get_executive_summary(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    """A one-paragraph, plain-English brief of this contract's current AI
    analysis for a non-legal stakeholder. Cached per analyzed version --
    returns the same summary on repeat views until the contract is
    re-analyzed into a new version, or the caller explicitly regenerates it."""
    try:
        return await get_executive_summary_service().get_summary(contract_id, str(user["uid"]))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ExecutiveSummaryError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except VertexAIError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.post("/{contract_id}/executive-summary/regenerate")
async def regenerate_executive_summary(contract_id: str, user: dict[str, Any] = Depends(get_current_user)):
    """Force a fresh summary even if a cached one exists for the current
    version -- for when a reviewer wants an up-to-date brief without waiting
    for the next re-analysis."""
    try:
        return await get_executive_summary_service().get_summary(contract_id, str(user["uid"]), force=True)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ExecutiveSummaryError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except VertexAIError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
