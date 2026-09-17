"""Pure deterministic matching and metric calculation for AI evaluations.

This module accepts finalized ground-truth records and isolated evaluation-run
findings. It never calls an AI provider and never writes production collections.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .evaluation import (
    EvaluationError,
    EvaluationMatchStatus,
    EvaluationMetrics,
    EvaluationMatch,
    EvaluationStatus,
    FindingSeverity,
)

EVALUATOR_VERSION = "1.0.0"
_UNKNOWN = "UNKNOWN"
_VALID = "VALID"
_INVALID = "INVALID"
_STOP_WORDS = {
    "a", "an", "and", "any", "are", "be", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with",
}
_STABLE_EVALUATION_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def text_tokens(value: Any) -> set[str]:
    return {token for token in normalize_text(value).split() if token not in _STOP_WORDS and len(token) > 1}


def numeric_tokens(value: Any) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", str(value or "")))


def semantic_conflict(left: Any, right: Any) -> bool:
    left_text = text_tokens(left) | set(normalize_text(left).split())
    right_text = text_tokens(right) | set(normalize_text(right).split())
    contrast_pairs = (("no", ""), ("not", ""), ("cause", "convenience"), ("excluded", "included"), ("prohibited", "permitted"))
    for first, second in contrast_pairs:
        if first and ((first in left_text) != (first in right_text)):
            return True
        if second and ((second in left_text) != (second in right_text)):
            return True
    return False


def overlap_score(left: Any, right: Any) -> float:
    left_tokens = text_tokens(left)
    right_tokens = text_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _equal_signal(left: Any, right: Any) -> bool | None:
    left_value = normalize_text(left)
    right_value = normalize_text(right)
    if not left_value or not right_value:
        return None
    return left_value == right_value


def _finding_text(record: dict[str, Any], *, ground_truth: bool) -> str:
    fields = ("expected_finding",) if ground_truth else ("finding", "title", "description")
    return " ".join(str(record.get(field) or "") for field in fields)


def _evidence_text(record: dict[str, Any], *, ground_truth: bool) -> str:
    fields = ("expected_evidence",) if ground_truth else ("evidence", "evidence_quote")
    return " ".join(str(record.get(field) or "") for field in fields)


def _evidence_grounding(ground_truth: dict[str, Any], ai: dict[str, Any]) -> tuple[str, str]:
    expected = str(ground_truth.get("expected_evidence") or "")
    actual = _evidence_text(ai, ground_truth=False)
    if not expected or not actual:
        return _UNKNOWN, "Evidence comparison unavailable because expected or AI evidence is missing."
    if semantic_conflict(expected, actual):
        return _INVALID, "Evidence contains a deterministic negation or contrast conflict."
    quote_score = overlap_score(expected, actual)
    if normalize_text(expected) in normalize_text(actual) or normalize_text(actual) in normalize_text(expected):
        return _VALID, f"Evidence text contains the normalized expected evidence (overlap={quote_score:.2f})."
    if quote_score >= 0.5:
        return _VALID, f"Evidence token overlap reached {quote_score:.2f}."
    return _INVALID, f"Evidence token overlap was only {quote_score:.2f}."


def _candidate_score(ground_truth: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
    category_match = _equal_signal(ground_truth.get("finding_category"), ai.get("finding_category") or ai.get("clause_type"))
    clause_match = _equal_signal(ground_truth.get("clause_reference"), ai.get("clause_reference") or ai.get("source_section"))
    evidence_score = overlap_score(ground_truth.get("expected_evidence"), _evidence_text(ai, ground_truth=False))
    finding_score = overlap_score(_finding_text(ground_truth, ground_truth=True), _finding_text(ai, ground_truth=False))
    evidence_match = evidence_score >= 0.5 if ground_truth.get("expected_evidence") and _evidence_text(ai, ground_truth=False) else None
    severity_match = _equal_signal(ground_truth.get("expected_severity"), ai.get("severity"))
    expected_numbers = numeric_tokens(_finding_text(ground_truth, ground_truth=True) + " " + ground_truth.get("expected_evidence", ""))
    actual_numbers = numeric_tokens(_finding_text(ai, ground_truth=False) + " " + _evidence_text(ai, ground_truth=False))
    numeric_match = expected_numbers == actual_numbers if expected_numbers and actual_numbers else None
    semantic_match = not semantic_conflict(_finding_text(ground_truth, ground_truth=True), _finding_text(ai, ground_truth=False))
    signals = [signal for signal in (category_match, clause_match, evidence_match) if signal is not None]
    positive_signals = sum(signal is True for signal in signals)
    score = (positive_signals / len(signals) if signals else 0.0) * 0.7 + finding_score * 0.3
    return {
        "category_match": category_match,
        "clause_match": clause_match,
        "evidence_match": evidence_match,
        "severity_match": severity_match,
        "numeric_match": numeric_match,
        "semantic_match": semantic_match,
        "evidence_score": evidence_score,
        "finding_score": finding_score,
        "score": min(1.0, score),
    }


def _determine_status(signals: dict[str, Any], tied: bool) -> EvaluationMatchStatus:
    if tied:
        return EvaluationMatchStatus.UNCERTAIN
    if signals.get("category_match") is False:
        return EvaluationMatchStatus.UNCERTAIN
    if signals.get("numeric_match") is False:
        return EvaluationMatchStatus.UNCERTAIN
    if signals.get("semantic_match") is False:
        return EvaluationMatchStatus.UNCERTAIN
    if signals.get("clause_match") is False and not (
        signals.get("category_match") is True
        and signals.get("evidence_match") is True
        and signals.get("finding_score", 0) >= 0.5
    ):
        return EvaluationMatchStatus.UNCERTAIN
    structural = [signals["category_match"], signals["clause_match"]]
    positive_structural = sum(value is True for value in structural)
    if signals.get("category_match") is True and signals.get("clause_match") is True:
        return EvaluationMatchStatus.MATCHED
    if signals["score"] >= 0.65 and positive_structural >= 1:
        return EvaluationMatchStatus.MATCHED
    if signals["score"] >= 0.4 and positive_structural == 0:
        return EvaluationMatchStatus.UNCERTAIN
    return EvaluationMatchStatus.UNCERTAIN


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class EvaluationResult:
    matches: list[dict[str, Any]]
    metrics: dict[str, Any]


class DeterministicEvaluationEngine:
    """Versioned, repeatable evaluator with no model or provider dependency."""

    evaluator_version = EVALUATOR_VERSION

    @staticmethod
    def _candidate_score(ground_truth: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
        return _candidate_score(ground_truth, ai)

    def evaluate(
        self,
        *,
        org_id: str,
        evaluation_run_id: str,
        dataset_version_id: str,
        ground_truth_findings: Iterable[dict[str, Any]],
        ai_findings: Iterable[dict[str, Any]],
        require_finalized: bool = True,
        evaluated_at: datetime | None = None,
    ) -> EvaluationResult:
        ground_truth = list(ground_truth_findings)
        ai = list(ai_findings)
        if require_finalized and any(record.get("review_status") != EvaluationStatus.FINALIZED.value for record in ground_truth):
            raise EvaluationError("Evaluation requires finalized ground-truth findings")
        if any(record.get("org_id") != org_id for record in [*ground_truth, *ai]):
            raise EvaluationError("Evaluation records must belong to the active organization")

        matches: list[dict[str, Any]] = []
        used_ai: set[str] = set()
        assigned: dict[str, tuple[str, dict[str, Any], dict[str, Any], bool]] = {}
        candidate_rows: list[tuple[float, str, str, dict[str, Any], dict[str, Any]]] = []
        for gt in ground_truth:
            gt_id = str(gt["ground_truth_id"])
            for item in ai:
                ai_id = str(item["evaluation_finding_id"])
                if item.get("contract_id") != gt.get("contract_id") or item.get("version_id") != gt.get("version_id"):
                    continue
                signals = self._candidate_score(gt, item)
                if signals["score"] <= 0:
                    continue
                if signals.get("category_match") is False and signals.get("clause_match") is False and signals["score"] < 0.4:
                    continue
                candidate_rows.append((signals["score"], gt_id, ai_id, item, signals))
        candidate_rows.sort(key=lambda row: (-row[0], row[1], row[2]))
        for index, (score, gt_id, ai_id, item, signals) in enumerate(candidate_rows):
            if gt_id in assigned or ai_id in used_ai:
                continue
            tied = any(
                other_gt == gt_id
                and other_ai not in used_ai
                and abs(score - other_score) < 0.0001
                and _candidate_fingerprint(signals) != _candidate_fingerprint(other_signals)
                for other_score, other_gt, other_ai, _, other_signals in candidate_rows[index + 1:]
            )
            assigned[gt_id] = (ai_id, item, signals, tied)
            used_ai.add(ai_id)

        evaluation_time = evaluated_at or _STABLE_EVALUATION_TIME
        for gt in sorted(ground_truth, key=lambda record: str(record["ground_truth_id"])):
            gt_id = str(gt["ground_truth_id"])
            assignment = assigned.get(gt_id)
            if assignment:
                ai_id, item, signals, tied = assignment
                status = _determine_status(signals, tied=False)
                if tied:
                    status = EvaluationMatchStatus.UNCERTAIN
                evidence_status, evidence_reason = _evidence_grounding(gt, item)
                severity_correct = signals["severity_match"]
                recommendation_correct = _equal_signal(gt.get("expected_recommendation"), item.get("recommendation"))
                rationale = (
                    f"contract_id and version_id matched; category_match={signals['category_match']}; "
                    f"clause_match={signals['clause_match']}; evidence_match={signals['evidence_match']}; "
                    f"finding_overlap={signals['finding_score']:.2f}; {evidence_reason}"
                )
                matches.append(self._match_record(org_id, evaluation_run_id, gt, item, status, signals, evidence_status, severity_correct, recommendation_correct, rationale, evaluation_time))
            else:
                matches.append(self._match_record(org_id, evaluation_run_id, gt, None, EvaluationMatchStatus.MISSED, {}, _UNKNOWN, None, None, "No unique deterministic candidate shared the same contract_id and version_id.", evaluation_time))

        for item in sorted(ai, key=lambda record: str(record["evaluation_finding_id"])):
            ai_id = str(item["evaluation_finding_id"])
            if ai_id in used_ai:
                continue
            matches.append(self._match_record(org_id, evaluation_run_id, None, item, EvaluationMatchStatus.FALSE_POSITIVE, {}, _UNKNOWN, None, None, "AI finding did not receive a one-to-one match to a finalized ground-truth finding.", evaluation_time))

        metrics = self._metrics(org_id, evaluation_run_id, matches)
        return EvaluationResult(matches=matches, metrics=metrics)

    def persist(self, result: EvaluationResult, *, matches_repository: Any, metrics_repository: Any) -> None:
        """Idempotently persist only evaluation collections."""
        for match in result.matches:
            matches_repository.set(match["evaluation_match_id"], match)
        metrics_repository.set(result.metrics["evaluation_metrics_id"], result.metrics)

    def _match_record(self, org_id: str, run_id: str, gt: dict[str, Any] | None, ai: dict[str, Any] | None, status: EvaluationMatchStatus, signals: dict[str, Any], evidence_status: str, severity_correct: bool | None, recommendation_correct: bool | None, rationale: str, evaluated_at: datetime) -> dict[str, Any]:
        gt_id = str((gt or {}).get("ground_truth_id") or "")
        ai_id = str((ai or {}).get("evaluation_finding_id") or "")
        contract_id = str((gt or ai or {}).get("contract_id") or "")
        version_id = str((gt or ai or {}).get("version_id") or "")
        record = EvaluationMatch(
            evaluation_match_id=_stable_id("match", run_id, self.evaluator_version, gt_id, ai_id, status.value),
            org_id=org_id,
            evaluation_run_id=run_id,
            ground_truth_id=gt_id or None,
            evaluation_finding_id=ai_id or None,
            contract_id=contract_id,
            version_id=version_id,
            status=status,
            category_match=signals.get("category_match"),
            clause_match=signals.get("clause_match"),
            evidence_match=signals.get("evidence_match"),
            numeric_match=signals.get("numeric_match"),
            severity_match=signals.get("severity_match"),
            severity_correct=severity_correct,
            expected_severity=(gt or {}).get("expected_severity"),
            ai_severity=(ai or {}).get("severity"),
            evidence_grounding=evidence_status,
            recommendation_correct=recommendation_correct,
            match_score=signals.get("score"),
            confidence=signals.get("score"),
            match_reason=rationale,
            rationale=rationale,
            evaluator_version=self.evaluator_version,
            created_at=evaluated_at,
        )
        return record.model_dump(mode="json")

    def _metrics(self, org_id: str, run_id: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
        tp = sum(item["status"] == EvaluationMatchStatus.MATCHED.value for item in matches)
        fp = sum(item["status"] == EvaluationMatchStatus.FALSE_POSITIVE.value for item in matches)
        fn = sum(item["status"] == EvaluationMatchStatus.MISSED.value for item in matches)
        uncertain = sum(item["status"] == EvaluationMatchStatus.UNCERTAIN.value for item in matches)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
        detected = [item for item in matches if item["status"] == EvaluationMatchStatus.MATCHED.value]
        severity_accuracy = _ratio([item["severity_correct"] for item in detected])
        critical = [item for item in matches if item.get("expected_severity") == FindingSeverity.CRITICAL.value]
        high_risk = [item for item in matches if item.get("expected_severity") in {FindingSeverity.CRITICAL.value, FindingSeverity.HIGH.value}]
        critical_recall = _ratio([item["status"] == EvaluationMatchStatus.MATCHED.value for item in critical])
        high_risk_recall = _ratio([item["status"] == EvaluationMatchStatus.MATCHED.value for item in high_risk])
        evidence_grounding = _ratio([item["evidence_grounding"] == _VALID for item in detected if item["evidence_grounding"] != _UNKNOWN])
        recommendation_accuracy = _ratio([item["recommendation_correct"] for item in detected if item["recommendation_correct"] is not None])
        return EvaluationMetrics(
            evaluation_metrics_id=_stable_id("metrics", run_id, self.evaluator_version),
            org_id=org_id,
            evaluation_run_id=run_id,
            precision=precision,
            recall=recall,
            f1=f1,
            severity_accuracy=severity_accuracy,
            critical_recall=critical_recall,
            high_risk_recall=high_risk_recall,
            evidence_grounding=evidence_grounding,
            recommendation_accuracy=recommendation_accuracy,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            uncertain_count=uncertain,
            evaluator_version=self.evaluator_version,
            calculated_at=_STABLE_EVALUATION_TIME,
        ).model_dump(mode="json")


def _ratio(values: list[Any]) -> float | None:
    if not values:
        return None
    return sum(value is True for value in values) / len(values)


def _candidate_fingerprint(signals: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(signals.get(key) for key in ("category_match", "clause_match", "evidence_match", "finding_score", "evidence_score"))
