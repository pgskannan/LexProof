"""Reusable contract-version analysis lifecycle."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException

from ..config import get_settings
from ..domains.passport.api.router import configure_passport_service
from ..domains.passport.service import PassportService
from ..domains.passport.utils.evidence import count_legal_evidence_findings
from ..domains.passport.utils.hashing import compute_sha256_hash
from ..repositories.firestore import EvidenceAnchorRepository, FirestoreRepository
from .audit import record_audit_event
from .analysis_prompt import (
    ANALYSIS_SYSTEM_PROMPT,
    build_analysis_prompt,
    build_playbook_text,
    parse_structured_analysis,
)
from .analysis_safety import sanitize_analysis_error as _sanitize_analysis_error
from .notification_prefs import get_notification_preferences
from .ethereum_anchor_service import get_ethereum_anchor_service
from .organizations import DEFAULT_PLAYBOOK_CLAUSES, contract_owner_or_org_admin
from .vertex_ai import VertexAIError, VertexGeminiProvider

logger = logging.getLogger(__name__)


def _structured_clauses(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = analysis.get("key_clauses", [])
    if not isinstance(clauses, list):
        return []
    structured = []
    for clause in clauses:
        if isinstance(clause, dict):
            text = clause.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            structured.append({
                **clause,
                "text": text,
                "hash": str(clause.get("hash") or compute_sha256_hash(text)),
            })
        elif isinstance(clause, str) and clause.strip():
            structured.append({"text": clause, "hash": compute_sha256_hash(clause)})
    return structured


def _load_playbook_clauses(repository_factory: Callable[[str], Any], org_id: str | None) -> list[dict[str, Any]]:
    """Benchmark clauses for this analysis: the org's customized playbook when

    one exists, else the built-in default -- so playbook benchmarking is
    always live, including for contracts with no org (e.g. the demo flow),
    never gated behind admin setup.
    """
    if org_id:
        try:
            org = repository_factory("organizations").get(org_id)
        except Exception:
            org = None
        clauses = (org or {}).get("playbook_clauses")
        if isinstance(clauses, list) and clauses:
            return clauses
    return DEFAULT_PLAYBOOK_CLAUSES


class VersionAnalysisService:
    """Run the existing analysis, passport, evidence, and anchor lifecycle."""

    def __init__(
        self,
        *,
        contracts: FirestoreRepository,
        versions: FirestoreRepository,
        repository_factory: Callable[[str], FirestoreRepository] = FirestoreRepository,
        anchor_repository_factory: Callable[[str], FirestoreRepository] = EvidenceAnchorRepository,
        provider_factory: Callable[[], VertexGeminiProvider] = VertexGeminiProvider,
        anchor_service_factory: Callable[..., Any] = get_ethereum_anchor_service,
        passport_service_factory: Callable[..., PassportService] = PassportService,
        passport_configurator: Callable[[PassportService], None] = configure_passport_service,
    ) -> None:
        self.contracts = contracts
        self.versions = versions
        self.repository_factory = repository_factory
        self.anchor_repository_factory = anchor_repository_factory
        self.provider_factory = provider_factory
        self.anchor_service_factory = anchor_service_factory
        self.passport_service_factory = passport_service_factory
        self.passport_configurator = passport_configurator

    def _create_notification(
        self,
        *,
        user_id: str,
        type_: str,
        title: str,
        message: str,
        contract_id: str | None = None,
        url: str | None = None,
    ) -> None:
        """Write an in-app notification for the signed-in user.

        Best-effort: notifications are a convenience layer over the same
        analysis lifecycle, not a system of record, so a write failure here
        (e.g. a transient Firestore hiccup) must never mask the real
        analysis result or error that triggered it.
        """
        try:
            preferences = get_notification_preferences(self.repository_factory, user_id)
            if not preferences.get(f"in_app_{type_}", True):
                return
            notifications = self.repository_factory("notifications")
            notification_id = str(uuid.uuid4())
            notifications.set(notification_id, {
                "id": notification_id,
                "owner_id": user_id,
                "type": type_,
                "title": title,
                "message": message,
                "contract_id": contract_id,
                "url": url,
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            logger.warning("Failed to write notification for user_id=%s", user_id, exc_info=True)

    def _find_passport(self, passports, version_id, passport_id=None):
        if passport_id:
            existing = passports.get(passport_id)
            if existing:
                return existing
        for passport in passports.stream():
            if passport.get("version_id") == version_id or (passport.get("metadata") or {}).get("version_id") == version_id:
                return passport
        return None

    @staticmethod
    def _matches_finding(record, finding):
        return all(record.get(key) == value for key, value in finding.items())

    @staticmethod
    def _matches_evidence(record, evidence):
        return (
            record.get("passport_id") == evidence.get("passport_id")
            and record.get("source_id") == evidence.get("source_id")
            and record.get("evidence_type") == evidence.get("evidence_type")
        )

    async def analyze_version(
        self,
        contract_id: str,
        version_id: str,
        user_id: str,
        *,
        anchor_evidence: bool = True,
    ) -> dict[str, Any]:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        if not contract_owner_or_org_admin(contract, user_id):
            raise HTTPException(status_code=403, detail="You are not authorized to analyze this contract")
        version = self.versions.get(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Contract version not found")
        if version.get("contract_id") != contract_id or not contract_owner_or_org_admin(contract, user_id):
            raise HTTPException(status_code=403, detail="You are not authorized to analyze this contract version")
        if contract.get("current_version_id") != version_id:
            raise HTTPException(status_code=409, detail="Only the current published version can be analyzed")
        document_text = version.get("document_text")
        if not isinstance(document_text, str) or not document_text.strip():
            raise HTTPException(status_code=422, detail="Contract version has no document text to analyze")

        passports = self.repository_factory("legal_passports")
        existing_passport_id = version.get("passport_id")
        existing_passport = self._find_passport(passports, version_id, existing_passport_id)
        if version.get("analysis_status") == "complete" and existing_passport:
            findings_count = sum(1 for finding in self.repository_factory("risk_findings").stream() if finding.get("version_id") == version_id and finding.get("owner_id") == user_id)
            evidence_count = sum(1 for evidence in self.repository_factory("evidence_records").stream() if evidence.get("passport_id") == existing_passport.get("passport_id") and evidence.get("owner_id") == user_id and evidence.get("evidence_type") != "metadata")
            # Re-arm the process-global passport service with this request's real
            # user/tenant scope even on this idempotent short-circuit path. Skipping
            # this (as the code previously did) means the global service stays on
            # whatever tenant it last had - "read-only" on a freshly (re)started
            # process that hasn't yet run a full (non-cached) analyze - so passport
            # list/lookup-by-contract and Time Machine calls silently see nothing
            # for a real, existing, correctly-owned passport until some other
            # request happens to take the full analysis path first.
            self.passport_configurator(self.passport_service_factory(None, user_id=user_id, tenant_id=user_id, repository=passports))
            return {"passport": existing_passport, "passport_id": existing_passport.get("passport_id"), "analysis_status": "complete", "finding_count": findings_count, "evidence_count": evidence_count}
        if version.get("analysis_status") == "processing":
            raise HTTPException(status_code=409, detail="Contract version analysis is already in progress")

        self.versions.set(version_id, {"analysis_status": "processing"}, merge=True)

        playbook_clauses = _load_playbook_clauses(self.repository_factory, contract.get("org_id"))
        playbook_text = build_playbook_text(playbook_clauses)

        class Request:
            # Production and the isolated benchmark runner build the identical
            # prompt from the shared, versioned builder (ANALYSIS_PROMPT_VERSION),
            # so a benchmark measures the AI behaviour production actually ships.
            prompt = build_analysis_prompt(document_text, playbook_text)
            model = None
            system_prompt = ANALYSIS_SYSTEM_PROMPT

        # Real, measured AI processing time (hardening item #3), timed directly
        # around the actual Gemini call below -- deliberately NOT derived from
        # broader lifecycle timestamps (e.g. version created_at vs. passport
        # created_at), which can silently include upload delay, developer
        # debugging/restarts, or a later re-analysis gap and so misrepresent
        # true AI processing time. Stays None when this call reuses a cached
        # analysis_snapshot instead of invoking Gemini again (the idempotent
        # short-circuit path a few lines below has already returned before
        # this point for a *complete* analysis; this is the rarer case of a
        # snapshot persisted by a prior attempt that didn't finish creating a
        # passport) -- there is no new measurement to report in that case.
        ai_analysis_duration_ms: float | None = None
        try:
            analysis = version.get("analysis_snapshot")
            if not isinstance(analysis, dict):
                provider = self.provider_factory()
                gemini_call_started = time.monotonic()
                response = await provider.complete(Request())
                ai_analysis_duration_ms = (time.monotonic() - gemini_call_started) * 1000
                try:
                    analysis = parse_structured_analysis(response.content)
                except ValueError:
                    logger.warning("Vertex AI structured analysis parse failed (length=%d, preview=%r)", len(response.content), " ".join(response.content[:500].split()))
                    raise
                self.versions.set(version_id, {"analysis_snapshot": analysis}, merge=True)
            findings = analysis["findings"]

            async def engine(document: str, policy: str) -> dict[str, Any]:
                return analysis

            passport_service = self.passport_service_factory(engine, user_id=user_id, tenant_id=user_id, repository=passports)
            if not existing_passport:
                passport = await passport_service.create_passport(
                    contract_id=contract_id,
                    contract_version=version["version_number"],
                    policy_version="default",
                    document_content=document_text,
                    metadata={"owner_id": user_id, "version_id": version_id, "risk_level": analysis.get("risk_level"), "key_clauses": analysis.get("key_clauses", []), "clauses": _structured_clauses(analysis), "compliance_items": analysis.get("compliance_items", []), "content_hash": version.get("content_hash")},
                    ai_analysis_duration_ms=ai_analysis_duration_ms,
                )
                existing_passport = {**passport.model_dump(mode="json"), "id": passport.passport_id, "owner_id": user_id, "version_id": version_id}
            passport_id = existing_passport.get("passport_id")
            now = datetime.now(timezone.utc).isoformat()
            passports.set(passport_id, {**existing_passport, "id": passport_id, "owner_id": user_id, "version_id": version_id, "risk_level": analysis.get("risk_level"), "findings_count": len(findings), "content_hash": version.get("content_hash"), "blockchain_status": "not_anchored", "analysis_timestamp": now})
            findings_repository = self.repository_factory("risk_findings")
            persisted_findings = list(findings_repository.stream())
            matched_finding_indexes: set[int] = set()
            for finding in findings:
                matching_index = next((index for index, item in enumerate(persisted_findings) if index not in matched_finding_indexes and item.get("version_id") == version_id and item.get("owner_id") == user_id and self._matches_finding(item, finding)), None)
                if matching_index is not None:
                    matched_finding_indexes.add(matching_index)
                    continue
                finding_id = str(uuid.uuid4())
                # Finding Evidence Integrity (hardening follow-up to Priority #1's
                # browser Publish smoke test): Gemini is instructed to return a
                # verbatim `evidence_quote` for each finding (see the prompt
                # above), but nothing previously checked that claim against the
                # actual source text before persisting it -- the mismatch was
                # only ever discovered later, at publish time, when
                # ProposalService.publish() runs the exact same `str.count()`
                # check (services/redline_proposals.py) as the last line of
                # defense before creating a new contract version. That guard is
                # deliberately left completely unchanged; this only moves
                # detection earlier, to the point where the mismatch can
                # actually be surfaced to a reviewer before they spend time
                # drafting and approving a redline that can never publish.
                # Intentionally strict and unnormalized (no whitespace/quote
                # normalization, no fuzzy matching, no second LLM call): if the
                # AI's claim of an exact quote can't be proven against the real
                # document bytes, that is the fact to record, not paper over.
                evidence_quote = finding.get("evidence_quote") or ""
                evidence_match_count = document_text.count(evidence_quote) if evidence_quote else 0
                finding_record = {
                    "id": finding_id,
                    "owner_id": user_id,
                    # Org-scoped reads (GET /api/findings with X-Org-Id) query
                    # by org_id; without it these findings were invisible there.
                    "org_id": contract.get("org_id"),
                    "contract_id": contract_id,
                    "version_id": version_id,
                    "contract_version": version["version_number"],
                    **finding,
                    # Denormalized from the analysis-level result (not part of the
                    # per-finding schema) onto every finding, mirroring how
                    # contract_version is already denormalized above -- lets the
                    # Findings UI show/filter by source language without a second
                    # lookup against the passport or version record.
                    "detected_language": analysis.get("detected_language"),
                    "detected_language_name": analysis.get("detected_language_name"),
                    "evidence_validation": "VALID" if evidence_match_count == 1 else "INVALID",
                    "evidence_match_count": evidence_match_count,
                    "created_at": now,
                }
                findings_repository.set(finding_id, finding_record)
                persisted_findings.append(finding_record)
            evidence_repository = self.repository_factory("evidence_records")
            evidence_items = await passport_service._create_evidence_items(passport_id, contract_id, version["version_number"], analysis)
            persisted_evidence = [
                item for item in evidence_repository.stream()
                if item.get("passport_id") == passport_id and item.get("owner_id") == user_id
            ]
            for evidence_item in evidence_items:
                if any(item.get("passport_id") == passport_id and item.get("owner_id") == user_id and self._matches_evidence(item, evidence_item) for item in persisted_evidence):
                    continue
                evidence_repository.set(evidence_item["evidence_id"], evidence_item)
                persisted_evidence.append(evidence_item)

            if anchor_evidence:
                anchor_repository = self.anchor_repository_factory("evidence_anchors")
                # anchor_service_factory defaults to get_ethereum_anchor_service, a
                # lazy singleton accessor: on its first call per process it
                # constructs a real BlockchainService, which does blocking network
                # I/O (connectivity check + an eth_chainId RPC call). Run that
                # construction on a worker thread so it can never stall the event
                # loop (hardening item #2; see ethereum_anchor_service.py's
                # get_ethereum_anchor_service for the full rationale) -- this is
                # safe regardless of what factory is injected (a synchronous test
                # fake just returns immediately from the worker thread).
                anchor_service = await asyncio.to_thread(
                    self.anchor_service_factory,
                    repository=anchor_repository,
                    evidence_repository=evidence_repository,
                )
                try:
                    for evidence_item in persisted_evidence:
                        # Phase 3F: pass through the real actor/tenant/version
                        # context already in scope on this request so the
                        # blockchain lifecycle audit events emitted inside
                        # anchor_evidence() are attributable and org-scoped,
                        # not just "system". Purely additive -- none of these
                        # keyword args affect anchoring behavior or idempotency.
                        await anchor_service.anchor_evidence(
                            evidence_item["evidence_id"],
                            actor_id=user_id,
                            org_id=contract.get("org_id"),
                            version_id=version_id,
                        )
                except Exception as exc:
                    # Log the real underlying cause (RPC error, on-chain revert reason, hash
                    # mismatch, etc.) before it is converted into the generic response below.
                    # Anchoring failure aborts the whole version analysis by design: leaving the
                    # version half-anchored with analysis_status "complete" would let the UI show
                    # a passport whose evidence integrity guarantee is not actually established
                    # yet. Retrying analyze_version is safe - analysis_snapshot and already-created
                    # findings/evidence/anchors are all reused idempotently.
                    logger.error(
                        "Ethereum anchoring failed for version_id=%s: %s", version_id, exc, exc_info=True
                    )
                    raise HTTPException(status_code=502, detail="Ethereum anchoring failed") from exc

            self.versions.set(version_id, {"analysis_status": "complete", "passport_id": passport_id}, merge=True)
            self.passport_configurator(passport_service)
            contract_name = contract.get("name") or contract.get("contract_name") or contract_id
            self._create_notification(
                user_id=user_id,
                type_="analysis_complete",
                title="Contract analysis complete",
                message=f'"{contract_name}" (v{version["version_number"]}) has a new legal passport with {len(findings)} finding(s).',
                contract_id=contract_id,
                url=f"/dashboard/contracts/{contract_id}",
            )
            record_audit_event(
                self.repository_factory,
                actor_id=user_id,
                action="passport.created",
                resource_type="legal_passport",
                resource_id=passport_id,
                resource_name=contract_name,
                contract_id=contract_id,
                summary=f"AI analysis complete for \"{contract_name}\" (v{version['version_number']}) -- {len(findings)} finding(s)",
                org_id=contract.get("org_id"),
            )
            return {"passport": existing_passport, "passport_id": passport_id, "analysis_status": "complete", "finding_count": len(findings), "evidence_count": count_legal_evidence_findings(evidence_items)}
        except HTTPException as exc:
            self._mark_analysis_failed(version_id, exc)
            if exc.status_code >= 500:
                self._notify_analysis_failed(user_id, contract_id, version_id)
            raise
        except VertexAIError as exc:
            self._mark_analysis_failed(version_id, exc)
            self._notify_analysis_failed(user_id, contract_id, version_id)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            self._mark_analysis_failed(version_id, exc)
            self._notify_analysis_failed(user_id, contract_id, version_id)
            raise HTTPException(status_code=502, detail="Vertex AI returned invalid structured analysis") from exc
        except Exception as exc:
            self._mark_analysis_failed(version_id, exc)
            self._notify_analysis_failed(user_id, contract_id, version_id)
            raise HTTPException(status_code=502, detail="Version analysis failed") from exc

    def _mark_analysis_failed(self, version_id: str, exc: BaseException) -> None:
        self.versions.set(
            version_id,
            {
                "analysis_status": "failed",
                "analysis_error": exc.__class__.__name__,
                "error_detail": _sanitize_analysis_error(exc),
            },
            merge=True,
        )

    def _notify_analysis_failed(self, user_id: str, contract_id: str, version_id: str) -> None:
        contract = self.contracts.get(contract_id) or {}
        version = self.versions.get(version_id) or {}
        contract_name = contract.get("name") or contract.get("contract_name") or contract_id
        version_number = version.get("version_number")
        label = f" (v{version_number})" if version_number else ""
        self._create_notification(
            user_id=user_id,
            type_="analysis_failed",
            title="Contract analysis failed",
            message=f'"{contract_name}"{label} analysis failed. Open the contract lifecycle page to retry.',
            contract_id=contract_id,
            url=f"/dashboard/contracts/{contract_id}",
        )
