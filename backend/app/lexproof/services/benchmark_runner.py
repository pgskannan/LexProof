"""Isolated AI benchmark runner.

Runs LexProof AI over the exact frozen contract versions of a *finalized*
benchmark dataset and stores the result as evaluation-run data only. It exists so
that AI accuracy can be measured without touching production analysis artifacts:
no ``risk_findings``, no ``legal_passports``, no ``evidence_records``, no
``evidence_anchors``, no notifications, no production audit events, and no
``contract_versions.analysis_status`` / ``analysis_snapshot`` writes.

Data flow (deliberately one-directional):

    dataset members (frozen contract versions)
        -> build_analysis_prompt(document_text, playbook_text)   [same prompt as production]
        -> provider (Vertex Gemini / injected fake)
        -> structured analysis
        -> map_ai_finding_to_run_finding
        -> evaluation_run_findings

    ... and only afterwards, in a separate step:

    evaluation_run_findings + FINALIZED ground truth
        -> DeterministicEvaluationEngine (unchanged, evaluator 1.0.0)
        -> evaluation_matches + evaluation_metrics

The runner never queries ground truth while producing AI output, and the prompt
is built from contract text and playbook only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .analysis_prompt import (
    ANALYSIS_PROMPT_VERSION,
    ANALYSIS_SYSTEM_PROMPT,
    build_analysis_prompt,
    build_playbook_text,
    parse_structured_analysis,
)
from .analysis_safety import sanitize_error_text
from .evaluation import EvaluationError, EvaluationRunStatus, EvaluationService, FindingSeverity
from .evaluation_engine import DeterministicEvaluationEngine
from .organizations import DEFAULT_PLAYBOOK_CLAUSES
from .vertex_ai import VertexGeminiProvider

MAX_CONTRACT_ERROR_CHARS = 300
MAX_ERROR_SUMMARY_CHARS = 1000
MAX_WARNINGS_PER_CONTRACT = 5

VALID_SEVERITIES = {severity.value for severity in FindingSeverity}


@dataclass(frozen=True)
class AnalysisRequest:
    """Provider request shape shared with production analysis."""

    prompt: str
    system_prompt: str = ANALYSIS_SYSTEM_PROMPT
    model: str | None = None


@dataclass(frozen=True)
class BenchmarkMember:
    """One frozen benchmark version, as stored in the evaluation dataset."""

    contract_id: str
    version_id: str
    content_hash: str
    document_text: str
    added_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def descriptor(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "version_id": self.version_id,
            "content_hash": self.content_hash,
            "added_at": self.added_at,
            "document_text_length": len(self.document_text),
        }


def stable_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def run_finding_id(run_id: str, version_id: str, finding_index: int, content_hash: str) -> str:
    """Deterministic run-finding id: sha256(run | version | index | content hash).

    Re-processing the same provider output inside the same run therefore targets
    the same document id, so it overwrites instead of duplicating.
    """
    digest = hashlib.sha256(f"{run_id}|{version_id}|{finding_index}|{content_hash}".encode("utf-8")).hexdigest()[:32]
    return f"runfind_{digest}"


def stable_run_key(
    *,
    dataset_version_id: str,
    provider: str,
    model: str,
    prompt_version: str,
    evaluator_version: str,
    version_ids: list[str],
) -> str:
    """Deterministic identity for a benchmark run.

    A timestamp is never part of the identity: the same dataset, provider, model,
    prompt version, evaluator version and exact member versions always produce the
    same key, so an accidental re-run reuses the existing run instead of creating
    an equivalent duplicate.
    """
    digest = hashlib.sha256(
        "|".join([dataset_version_id, provider, model, prompt_version, evaluator_version, *version_ids]).encode("utf-8")
    ).hexdigest()[:32]
    return f"runkey_{digest}"


def normalize_severity(value: Any) -> str | None:
    """Normalize an AI severity to the evaluation enum, or None if unrepresentable."""
    if value is None:
        return None
    candidate = str(value).strip().upper()
    return candidate if candidate in VALID_SEVERITIES else None


def map_ai_finding_to_run_finding(
    finding: dict[str, Any],
    *,
    contract_id: str,
    version_id: str,
    provider: str,
    model: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Map one AI finding onto the evaluation-run finding schema.

    Only fields the model actually returned are copied (title/description ->
    finding, evidence_quote -> evidence, source_section -> clause_reference,
    clause_type -> finding_category, severity, recommendation). Nothing is
    invented: a finding whose severity cannot be represented in the evaluation
    severity scale is returned as ``(None, warning)`` so the caller can record it
    rather than fabricate a legal severity.
    """
    if not isinstance(finding, dict):
        return None, "AI finding was not a JSON object and was omitted."

    severity = normalize_severity(finding.get("severity"))
    if severity is None:
        return None, f"AI finding severity {finding.get('severity')!r} is outside LOW/MEDIUM/HIGH/CRITICAL and was omitted."

    category = str(finding.get("clause_type") or finding.get("finding_category") or "Other").strip() or "Other"
    clause_reference = str(finding.get("source_section") or finding.get("clause_reference") or "").strip()
    body = str(finding.get("description") or finding.get("title") or "").strip()
    evidence = str(finding.get("evidence_quote") or finding.get("evidence") or "").strip()
    recommendation = finding.get("recommendation")
    recommendation = str(recommendation).strip() if isinstance(recommendation, str) and recommendation.strip() else None

    return (
        {
            "contract_id": contract_id,
            "version_id": version_id,
            "finding_category": category,
            "clause_reference": clause_reference,
            "severity": severity,
            "finding": body,
            "evidence": evidence,
            "recommendation": recommendation,
            "provider": provider,
            "model": model,
        },
        None,
    )


def default_playbook_provider(evaluation: EvaluationService, org_id: str | None) -> list[dict[str, Any]]:
    """Same playbook source production analysis uses (org playbook, else default)."""
    organization = None
    if org_id:
        organizations = getattr(evaluation.organizations, "orgs", None)
        if organizations is not None:
            try:
                organization = organizations.get(org_id)
            except Exception:
                organization = None
    clauses = (organization or {}).get("playbook_clauses")
    if isinstance(clauses, list) and clauses:
        return list(clauses)
    return list(DEFAULT_PLAYBOOK_CLAUSES)


def resolve_provider_model(provider_client: Any, requested: str | None) -> str:
    """Resolve the model a run analyses with, never inventing one.

    Providers expose their model list differently: ``VertexGeminiProvider`` has
    ``supported_models`` as a *property* (a plain list), while test doubles
    expose it as a method. Both must resolve to the real model name -- reading
    only the callable form silently downgraded the model to ``"unknown"``, which
    would have been recorded as provenance *and* sent to the Vertex SDK.
    """
    if requested:
        return str(requested)
    supported = getattr(provider_client, "supported_models", None)
    if callable(supported):
        supported = supported()
    if isinstance(supported, (list, tuple)) and supported:
        return str(supported[0])
    configured = getattr(getattr(provider_client, "settings", None), "gemini_model", None)
    return str(configured) if configured else "unknown"


class BenchmarkRunService:
    """Executes an isolated benchmark run and hands its output to the evaluator."""

    def __init__(
        self,
        *,
        evaluation: EvaluationService | None = None,
        provider_factory: Callable[[], Any] | None = None,
        playbook_provider: Callable[[str | None], list[dict[str, Any]]] | None = None,
        evaluator: DeterministicEvaluationEngine | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.evaluation = evaluation or EvaluationService()
        self.provider_factory = provider_factory or VertexGeminiProvider
        self.playbook_provider = playbook_provider
        self.evaluator = evaluator or DeterministicEvaluationEngine()
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ members
    def dataset_members(self, member: dict[str, Any], dataset_version_id: str) -> tuple[dict[str, Any], list[BenchmarkMember]]:
        """Load the frozen benchmark versions in deterministic dataset order.

        The exact member (contract_id, version_id) pairs are used as stored; the
        contract's ``current_version_id`` is never substituted, because this
        benchmark exists to measure those frozen versions. Ordering is by
        ``added_at`` so the run is reproducible.

        Only the dataset and its member rows are read here -- deliberately not the
        review workspace payload, which contains the human ground truth: the AI
        phase must not touch the answer key at all.
        """
        dataset = self.evaluation.get_dataset(member, dataset_version_id)
        rows = sorted(
            self.evaluation.members.query(equal={"dataset_version_id": dataset_version_id}),
            key=lambda row: str(row.get("added_at") or ""),
        )
        if not rows:
            raise EvaluationError("Benchmark dataset has no contract members to analyse")

        members: list[BenchmarkMember] = []
        for row in rows:
            contract_id = str(row.get("contract_id") or "")
            version_id = str(row.get("version_id") or "")
            contract = self.evaluation.contracts.get(contract_id) or {}
            version = self.evaluation.versions.get(version_id) or {}
            if not contract:
                raise EvaluationError(f"Benchmark member contract not found: {contract_id}")
            if not version:
                raise EvaluationError(f"Benchmark member version not found: {version_id}")
            if str(version.get("contract_id") or "") != contract_id:
                raise EvaluationError(f"Benchmark member version {version_id} does not belong to contract {contract_id}")
            if str(contract.get("org_id") or "") != str(dataset.get("org_id") or ""):
                raise EvaluationError(f"Benchmark member contract {contract_id} belongs to a different organization")
            document_text = version.get("document_text") or ""
            if not str(document_text).strip():
                raise EvaluationError(f"Benchmark member version {version_id} has no document text to analyse")
            members.append(
                BenchmarkMember(
                    contract_id=contract_id,
                    version_id=version_id,
                    content_hash=str(version.get("content_hash") or stable_text_hash(document_text)),
                    document_text=document_text,
                    added_at=str(row.get("added_at") or ""),
                )
            )
        return dataset, members

    def _playbook_text(self, org_id: str | None) -> str:
        provider = self.playbook_provider
        clauses = provider(org_id) if provider else default_playbook_provider(self.evaluation, org_id)
        return build_playbook_text(clauses)

    # --------------------------------------------------------------- run start
    async def start_run(
        self,
        member: dict[str, Any],
        *,
        dataset_version_id: str,
        provider: str | None = None,
        model: str | None = None,
        model_version: str | None = None,
        prompt_version: str = ANALYSIS_PROMPT_VERSION,
        idempotency_key: str | None = None,
        evaluate_after: bool = True,
    ) -> dict[str, Any]:
        """Create (or reuse) a run and analyse every benchmark version."""
        dataset, members = self.dataset_members(member, dataset_version_id)
        provider_client = self.provider_factory()
        provider_name = provider or str(getattr(provider_client, "provider_name", "") or "unknown")
        resolved_model = resolve_provider_model(provider_client, model)
        evaluator_version = self.evaluator.evaluator_version

        key = idempotency_key or stable_run_key(
            dataset_version_id=dataset_version_id,
            provider=provider_name,
            model=resolved_model,
            prompt_version=prompt_version,
            evaluator_version=evaluator_version,
            version_ids=[item.version_id for item in members],
        )
        existing = self.evaluation.find_run_by_idempotency_key(
            member, dataset_version_id=dataset_version_id, idempotency_key=key
        )
        if existing:
            metrics = self.evaluation.get_run_metrics(member, existing["evaluation_run_id"]) if evaluate_after else None
            return {"run": existing, "metrics": metrics, "reused": True}

        run = self.evaluation.create_run(
            member,
            dataset_version_id=dataset_version_id,
            provider=provider_name,
            model=resolved_model,
            model_version=model_version,
            prompt_version=prompt_version,
            evaluator_version=evaluator_version,
            idempotency_key=key,
            dataset_members=[item.descriptor() for item in members],
        )
        run_id = run["evaluation_run_id"]
        run = self.evaluation.update_run(member, run_id, status=EvaluationRunStatus.RUNNING.value)

        org_id = str(dataset.get("org_id") or run.get("org_id") or "")
        playbook_text = self._playbook_text(org_id)
        contract_errors: dict[str, str] = {}
        warnings: dict[str, list[str]] = {}
        failed_contract_ids: list[str] = []
        succeeded = 0

        for item in members:
            try:
                analysis = await self._analyze(provider_client, model=resolved_model, document_text=item.document_text, playbook_text=playbook_text)
            except Exception as exc:  # provider, transport, or parse failure for this contract
                failed_contract_ids.append(item.contract_id)
                contract_errors[item.contract_id] = sanitize_error_text(
                    f"{exc.__class__.__name__}: {exc}", limit=MAX_CONTRACT_ERROR_CHARS
                )
                continue
            succeeded += 1
            contract_warnings = self._persist_findings(
                member,
                run_id=run_id,
                item=item,
                analysis=analysis,
                provider=provider_name,
                model=resolved_model,
            )
            if contract_warnings:
                warnings[item.contract_id] = contract_warnings[:MAX_WARNINGS_PER_CONTRACT]

        if not failed_contract_ids:
            status = EvaluationRunStatus.COMPLETED.value
        elif succeeded:
            status = EvaluationRunStatus.PARTIAL.value
        else:
            status = EvaluationRunStatus.FAILED.value

        updates: dict[str, Any] = {
            "status": status,
            "completed_at": self._now().isoformat(),
            "failed_contract_ids": failed_contract_ids,
            "contract_errors": contract_errors,
            "ai_finding_count": self.evaluation.count_run_findings(member, run_id),
            "error_summary": self._error_summary(failed_contract_ids, contract_errors, len(members)),
        }
        if warnings:
            updates["contract_warnings"] = warnings
        run = self.evaluation.update_run(member, run_id, **updates)

        metrics = None
        if evaluate_after and status in {EvaluationRunStatus.COMPLETED.value, EvaluationRunStatus.PARTIAL.value}:
            metrics = await self.evaluate_run(member, run_id)
        return {"run": run, "metrics": metrics, "reused": False}

    async def _analyze(self, provider_client: Any, *, model: str, document_text: str, playbook_text: str) -> dict[str, Any]:
        request = AnalysisRequest(prompt=build_analysis_prompt(document_text, playbook_text), model=model)
        response = await provider_client.complete(request)
        content = getattr(response, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise EvaluationError("AI provider returned no analysis content")
        return parse_structured_analysis(content)

    def _persist_findings(
        self,
        member: dict[str, Any],
        *,
        run_id: str,
        item: BenchmarkMember,
        analysis: dict[str, Any],
        provider: str,
        model: str,
    ) -> list[str]:
        raw_findings = analysis.get("findings")
        if not isinstance(raw_findings, list):
            raise EvaluationError("AI analysis omitted findings")
        warnings: list[str] = []
        for index, raw in enumerate(raw_findings):
            mapped, warning = map_ai_finding_to_run_finding(
                raw, contract_id=item.contract_id, version_id=item.version_id, provider=provider, model=model
            )
            if mapped is None:
                warnings.append(warning or "AI finding was omitted during mapping.")
                continue
            self.evaluation.upsert_run_finding(
                member, run_id, run_finding_id(run_id, item.version_id, index, item.content_hash), **mapped
            )
        return warnings

    def _error_summary(self, failed_contract_ids: list[str], contract_errors: dict[str, str], total: int) -> str | None:
        if not failed_contract_ids:
            return None
        first_contract = failed_contract_ids[0]
        first_error = contract_errors.get(first_contract, "")
        summary = f"{len(failed_contract_ids)} of {total} benchmark contracts failed. First: {first_contract}: {first_error}"
        return sanitize_error_text(summary, limit=MAX_ERROR_SUMMARY_CHARS)

    # ---------------------------------------------------------------- evaluate
    async def evaluate_run(self, member: dict[str, Any], evaluation_run_id: str) -> dict[str, Any]:
        """Score an existing run with the deterministic evaluator (no new logic)."""
        run = self.evaluation.find_run(member, evaluation_run_id)
        if run.get("status") not in {EvaluationRunStatus.COMPLETED.value, EvaluationRunStatus.PARTIAL.value}:
            raise EvaluationError("Only completed or partially completed runs can be evaluated")

        ground_truth = self.evaluation.list_ground_truth_findings(member, run["dataset_version_id"])
        if not ground_truth:
            raise EvaluationError("Evaluation requires finalized ground-truth findings")
        ai_findings = self.evaluation.list_run_findings(member, evaluation_run_id)

        result = self.evaluator.evaluate(
            org_id=str(run["org_id"]),
            evaluation_run_id=evaluation_run_id,
            dataset_version_id=str(run["dataset_version_id"]),
            ground_truth_findings=ground_truth,
            ai_findings=ai_findings,
        )
        self.evaluator.persist(result, matches_repository=self.evaluation.matches, metrics_repository=self.evaluation.metrics)
        self.evaluation.update_run(
            member,
            evaluation_run_id,
            evaluator_version=self.evaluator.evaluator_version,
            evaluated_at=self._now().isoformat(),
        )
        return result.metrics

    # ----------------------------------------------------------- results reader
    def run_report(self, member: dict[str, Any], evaluation_run_id: str) -> dict[str, Any]:
        """Run status + metrics for humans. Never returns ground-truth content."""
        run = self.evaluation.find_run(member, evaluation_run_id)
        metrics = self.evaluation.get_run_metrics(member, evaluation_run_id)
        return {
            "evaluation_run_id": run.get("evaluation_run_id"),
            "status": run.get("status"),
            "dataset_version_id": run.get("dataset_version_id"),
            "provider": run.get("provider"),
            "model": run.get("model"),
            "model_version": run.get("model_version"),
            "prompt_version": run.get("prompt_version"),
            "evaluator_version": run.get("evaluator_version"),
            "created_by": run.get("created_by"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
            "evaluated_at": run.get("evaluated_at"),
            "contract_count": run.get("contract_count"),
            "ground_truth_count": run.get("ground_truth_count"),
            "ai_finding_count": run.get("ai_finding_count"),
            "dataset_members": run.get("dataset_members") or [],
            "failed_contract_ids": run.get("failed_contract_ids") or [],
            "contract_errors": run.get("contract_errors") or {},
            "contract_warnings": run.get("contract_warnings") or {},
            "error_summary": run.get("error_summary"),
            "metrics": self._metrics_report(metrics),
        }

    @staticmethod
    def _metrics_report(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
        if not metrics:
            return None
        return {
            key: metrics.get(key) for key in (
                "precision", "recall", "f1", "severity_accuracy", "critical_recall", "high_risk_recall",
                "evidence_grounding", "recommendation_accuracy", "true_positives", "false_positives",
                "false_negatives", "uncertain_count", "evaluator_version", "calculated_at",
            )
        }
