"""Deterministic evaluation-engine fixtures; not product accuracy claims."""

from copy import deepcopy
from itertools import permutations

import pytest

from app.lexproof.services.evaluation import EvaluationError, EvaluationMatchStatus
from app.lexproof.services.evaluation_engine import DeterministicEvaluationEngine
from tests.fakes import FakeRepository

ORG_ID = "org-1"
RUN_ID = "run-1"
DATASET_ID = "dataset-v1"


def gt(gt_id, category, clause, severity, finding, evidence, recommendation="Review the clause."):
    return {
        "ground_truth_id": gt_id,
        "org_id": ORG_ID,
        "dataset_version_id": DATASET_ID,
        "contract_id": "contract-1",
        "version_id": "version-1",
        "finding_category": category,
        "clause_reference": clause,
        "expected_severity": severity,
        "expected_finding": finding,
        "expected_evidence": evidence,
        "expected_recommendation": recommendation,
        "review_status": "FINALIZED",
    }


def ai(ai_id, category, clause, severity, finding, evidence, recommendation="Review the clause."):
    return {
        "evaluation_finding_id": ai_id,
        "org_id": ORG_ID,
        "dataset_version_id": DATASET_ID,
        "evaluation_run_id": RUN_ID,
        "contract_id": "contract-1",
        "version_id": "version-1",
        "finding_category": category,
        "clause_reference": clause,
        "severity": severity,
        "finding": finding,
        "evidence": evidence,
        "recommendation": recommendation,
    }


BASE_GT = [
    gt("g1", "liability cap", "Section 7", "HIGH", "Liability cap is below the approved standard", "liability shall not exceed 10,000"),
    gt("g2", "termination", "Section 8", "MEDIUM", "Termination notice is one-sided", "customer may terminate with thirty days notice"),
    gt("g3", "governing law", "Section 9", "LOW", "Governing law is unfavorable", "agreement governed by the laws of Delaware"),
]
BASE_AI = [
    ai("a1", "liability cap", "Section 7", "HIGH", "Liability cap is below the approved standard", "liability shall not exceed 10,000"),
    ai("a2", "termination", "Section 8", "LOW", "Termination notice is one-sided", "customer may terminate with thirty days notice"),
    ai("a3", "confidentiality", "Section 10", "HIGH", "Confidentiality obligation is broad", "all information must remain confidential"),
]


def evaluate(ground_truth=BASE_GT, ai_findings=BASE_AI):
    return DeterministicEvaluationEngine().evaluate(
        org_id=ORG_ID,
        evaluation_run_id=RUN_ID,
        dataset_version_id=DATASET_ID,
        ground_truth_findings=ground_truth,
        ai_findings=ai_findings,
    )


def by_status(result):
    return {item["status"]: item for item in result.matches if item.get("ground_truth_id")}


def test_fixture_counts_and_metrics_are_calculated_from_matches():
    result = evaluate()
    g1_match = next(item for item in result.matches if item.get("ground_truth_id") == "g1")
    assert g1_match["evaluation_finding_id"] == "a1"
    assert result.metrics["true_positives"] == 2
    assert result.metrics["false_positives"] == 1
    assert result.metrics["false_negatives"] == 1
    assert result.metrics["precision"] == pytest.approx(2 / 3)
    assert result.metrics["recall"] == pytest.approx(2 / 3)
    assert result.metrics["f1"] == pytest.approx(2 / 3)
    assert result.metrics["severity_accuracy"] == pytest.approx(0.5)
    assert result.metrics["evaluator_version"] == "1.0.0"


def test_severity_mismatch_keeps_detection_matched():
    result = evaluate(ground_truth=BASE_GT[:1], ai_findings=[BASE_AI[1] | {"finding_category": "liability cap", "clause_reference": "Section 7"}])
    match = result.matches[0]
    assert match["status"] == "MATCHED"
    assert match["severity_correct"] is False


def test_category_and_clause_conflicts_are_uncertain():
    category_conflict = evaluate(ground_truth=BASE_GT[:1], ai_findings=[ai("a1", "termination", "Section 7", "HIGH", BASE_GT[0]["expected_finding"], BASE_GT[0]["expected_evidence"])])
    assert category_conflict.matches[0]["status"] == "UNCERTAIN"

    clause_conflict = evaluate(ground_truth=BASE_GT[:1], ai_findings=[ai("a1", "liability cap", "Section 99", "HIGH", BASE_GT[0]["expected_finding"], "unrelated evidence")])
    assert clause_conflict.matches[0]["status"] == "UNCERTAIN"


def test_evidence_grounding_is_separate_from_detection():
    result = evaluate(ground_truth=BASE_GT[:1], ai_findings=[ai("a1", "liability cap", "Section 7", "HIGH", BASE_GT[0]["expected_finding"], "different evidence entirely")])
    assert result.matches[0]["status"] == "MATCHED"
    assert result.matches[0]["evidence_grounding"] == "INVALID"


def test_duplicate_ai_findings_are_one_to_one():
    duplicate = BASE_AI[0] | {"evaluation_finding_id": "a1-duplicate"}
    result = evaluate(ground_truth=BASE_GT[:1], ai_findings=[BASE_AI[0], duplicate])
    assert sum(item["status"] == "MATCHED" for item in result.matches) == 1
    assert sum(item["status"] == "FALSE_POSITIVE" for item in result.matches) == 1


def test_duplicate_ground_truth_candidates_are_not_double_matched():
    duplicate = BASE_GT[0] | {"ground_truth_id": "g1-duplicate"}
    result = evaluate(ground_truth=[BASE_GT[0], duplicate], ai_findings=[BASE_AI[0]])
    assert sum(item["status"] == "MATCHED" for item in result.matches) == 1
    assert sum(item["status"] == "MISSED" for item in result.matches) == 1


def test_critical_and_high_risk_recall_use_expected_severity():
    ground_truth = [gt("g-critical", "liability cap", "Section 7", "CRITICAL", "Critical cap issue", "cap text"), gt("g-high", "termination", "Section 8", "HIGH", "High termination issue", "termination text")]
    ai_findings = [ai("a-critical", "liability cap", "Section 7", "MEDIUM", "Critical cap issue", "cap text")]
    result = evaluate(ground_truth=ground_truth, ai_findings=ai_findings)
    assert result.metrics["critical_recall"] == pytest.approx(1.0)
    assert result.metrics["high_risk_recall"] == pytest.approx(0.5)


def test_zero_denominators_and_no_finalized_ground_truth_are_not_claimed_as_accuracy():
    empty = evaluate(ground_truth=[], ai_findings=[])
    assert empty.metrics["precision"] is None
    assert empty.metrics["recall"] is None
    assert empty.metrics["f1"] is None
    assert empty.metrics["true_positives"] == 0

    not_finalized = deepcopy(BASE_GT[:1])
    not_finalized[0]["review_status"] = "DRAFT"
    with pytest.raises(EvaluationError):
        evaluate(ground_truth=not_finalized, ai_findings=[])


def test_tenant_mismatch_is_rejected():
    foreign = deepcopy(BASE_AI[:1])
    foreign[0]["org_id"] = "org-2"
    with pytest.raises(EvaluationError):
        evaluate(ground_truth=BASE_GT[:1], ai_findings=foreign)


def test_idempotent_persistence_and_production_isolation():
    result = evaluate()
    matches = FakeRepository("evaluation_matches")
    metrics = FakeRepository("evaluation_metrics")
    engine = DeterministicEvaluationEngine()
    engine.persist(result, matches_repository=matches, metrics_repository=metrics)
    engine.persist(result, matches_repository=matches, metrics_repository=metrics)
    assert len(FakeRepository.stores["evaluation_matches"]) == len(result.matches)
    assert len(FakeRepository.stores["evaluation_metrics"]) == 1
    assert "risk_findings" not in FakeRepository.stores
    assert "contract_versions" not in FakeRepository.stores
    assert "legal_passports" not in FakeRepository.stores
    assert "evidence_records" not in FakeRepository.stores
    assert "redline_proposals" not in FakeRepository.stores


def test_same_category_different_clause_is_not_matched_without_corroboration():
    result = evaluate(ground_truth=BASE_GT[:1], ai_findings=[ai("a1", "liability cap", "Section 19", "HIGH", "Liability cap issue", "Section 19 discusses liability")])
    assert result.matches[0]["status"] == "UNCERTAIN"


def test_same_clause_different_finding_is_uncertain():
    result = evaluate(ground_truth=BASE_GT[:1], ai_findings=[ai("a1", "indemnification", "Section 7", "HIGH", "Indemnification is one-sided", "Section 7 discusses indemnification")])
    assert result.matches[0]["status"] == "UNCERTAIN"


def test_similar_words_with_different_legal_meaning_are_not_matched():
    result = evaluate(
        ground_truth=[gt("g1", "termination", "Section 4", "HIGH", "termination for convenience", "party may terminate for convenience")],
        ai_findings=[ai("a1", "termination", "Section 4", "HIGH", "termination for cause", "party may terminate for cause")],
    )
    assert result.matches[0]["status"] == "UNCERTAIN"
    assert result.matches[0]["evidence_grounding"] == "INVALID"


def test_generic_overlap_does_not_create_match():
    result = evaluate(
        ground_truth=[gt("g1", "liability cap", "Section 7", "HIGH", "limitation of liability", "Section 7 limits liability to fees paid")],
        ai_findings=[ai("a1", "confidentiality", "Section 12", "HIGH", "limitation of liability", "Section 12 discusses liability")],
    )
    assert result.matches[0]["status"] == "MISSED"
    assert any(item["status"] == "FALSE_POSITIVE" for item in result.matches)


def test_negation_and_numeric_difference_are_conservative():
    negation = evaluate(
        ground_truth=[gt("g1", "damages", "Section 2", "HIGH", "No consequential damages are excluded", "No consequential damages are excluded")],
        ai_findings=[ai("a1", "damages", "Section 2", "HIGH", "Consequential damages are excluded", "Consequential damages are excluded")],
    )
    assert negation.matches[0]["status"] in {"UNCERTAIN", "MATCHED"}
    assert negation.matches[0]["evidence_grounding"] == "INVALID"

    numeric = evaluate(
        ground_truth=[gt("g1", "liability cap", "Section 7", "HIGH", "Liability capped at 1M", "Liability capped at $1M")],
        ai_findings=[ai("a1", "liability cap", "Section 7", "HIGH", "Liability capped at 10M", "Liability capped at $10M")],
    )
    assert numeric.matches[0]["status"] == "UNCERTAIN"
    assert numeric.matches[0]["numeric_match"] is False


def test_section_collision_and_evidence_quote_mismatch_do_not_ground():
    result = evaluate(
        ground_truth=[gt("g1", "liability", "Section 7", "HIGH", "Liability is capped", "Section 7 limits liability")],
        ai_findings=[ai("a1", "confidentiality", "Section 7", "HIGH", "Confidentiality is broad", "Section 7 requires confidentiality")],
    )
    assert result.matches[0]["status"] == "UNCERTAIN"
    assert result.matches[0]["evidence_grounding"] == "INVALID"


def test_recommendation_mismatch_does_not_change_detection():
    result = evaluate(
        ground_truth=[gt("g1", "liability cap", "Section 7", "HIGH", "Liability cap issue", "Liability is capped", "Increase liability cap to 5M")],
        ai_findings=[ai("a1", "liability cap", "Section 7", "HIGH", "Liability cap issue", "Liability is capped", "Remove liability cap")],
    )
    assert result.matches[0]["status"] == "MATCHED"
    assert result.matches[0]["recommendation_correct"] is False


def test_five_near_identical_ai_findings_match_at_most_one():
    candidates = [BASE_AI[0] | {"evaluation_finding_id": f"a{i}"} for i in range(5)]
    result = evaluate(ground_truth=BASE_GT[:1], ai_findings=candidates)
    assert sum(item["status"] == "MATCHED" for item in result.matches) == 1
    assert sum(item["status"] == "FALSE_POSITIVE" for item in result.matches) == 4


def test_one_ai_finding_cannot_match_five_ground_truth_findings():
    ground_truth = [BASE_GT[0] | {"ground_truth_id": f"g{i}"} for i in range(5)]
    result = evaluate(ground_truth=ground_truth, ai_findings=BASE_AI[:1])
    assert sum(item["status"] == "MATCHED" for item in result.matches) == 1
    assert sum(item["status"] == "MISSED" for item in result.matches) == 4


def test_order_independence_and_100_run_determinism():
    engine = DeterministicEvaluationEngine()
    baseline = engine.evaluate(org_id=ORG_ID, evaluation_run_id=RUN_ID, dataset_version_id=DATASET_ID, ground_truth_findings=BASE_GT, ai_findings=BASE_AI)
    baseline_pairs = [(item["ground_truth_id"], item["evaluation_finding_id"], item["status"], item["match_score"]) for item in baseline.matches]
    for index in range(100):
        result = engine.evaluate(
            org_id=ORG_ID,
            evaluation_run_id=RUN_ID,
            dataset_version_id=DATASET_ID,
            ground_truth_findings=list(reversed(BASE_GT)) if index % 2 else BASE_GT,
            ai_findings=list(reversed(BASE_AI)) if index % 3 else BASE_AI,
        )
        assert [(item["ground_truth_id"], item["evaluation_finding_id"], item["status"], item["match_score"]) for item in result.matches] == baseline_pairs
        assert result.metrics["precision"] == baseline.metrics["precision"]
        assert result.metrics["recall"] == baseline.metrics["recall"]
        assert result.metrics["f1"] == baseline.metrics["f1"]
        assert [item["evaluation_match_id"] for item in result.matches] == [item["evaluation_match_id"] for item in baseline.matches]


def test_metric_invariants_and_zero_denominators():
    for result in (
        evaluate(ground_truth=[], ai_findings=[]),
        evaluate(ground_truth=BASE_GT, ai_findings=[]),
        evaluate(ground_truth=[], ai_findings=BASE_AI),
    ):
        metrics = result.metrics
        for key in ("precision", "recall", "f1", "severity_accuracy", "critical_recall", "high_risk_recall", "evidence_grounding", "recommendation_accuracy"):
            assert metrics[key] is None or 0 <= metrics[key] <= 1
        assert metrics["true_positives"] >= 0
        assert metrics["false_positives"] >= 0
        assert metrics["false_negatives"] >= 0


def test_evaluator_version_changes_historical_ids():
    first = evaluate()

    class NextEvaluator(DeterministicEvaluationEngine):
        evaluator_version = "1.1.0"

    second = NextEvaluator().evaluate(org_id=ORG_ID, evaluation_run_id=RUN_ID, dataset_version_id=DATASET_ID, ground_truth_findings=BASE_GT, ai_findings=BASE_AI)
    assert first.metrics["evaluator_version"] == "1.0.0"
    assert second.metrics["evaluator_version"] == "1.1.0"
    assert first.metrics["evaluation_metrics_id"] != second.metrics["evaluation_metrics_id"]
    assert first.matches[0]["evaluation_match_id"] != second.matches[0]["evaluation_match_id"]


def test_equal_score_conflicting_candidates_are_uncertain():
    class TieEvaluator(DeterministicEvaluationEngine):
        def _candidate_score(self, ground_truth, ai_finding):
            return {
                "category_match": ai_finding["evaluation_finding_id"] == "a1",
                "clause_match": ai_finding["evaluation_finding_id"] == "a2",
                "evidence_match": None,
                "severity_match": True,
                "numeric_match": True,
                "semantic_match": True,
                "evidence_score": 0.0,
                "finding_score": 1.0,
                "score": 0.8,
            }

    result = TieEvaluator().evaluate(
        org_id=ORG_ID,
        evaluation_run_id=RUN_ID,
        dataset_version_id=DATASET_ID,
        ground_truth_findings=BASE_GT[:1],
        ai_findings=[BASE_AI[0] | {"evaluation_finding_id": "a1"}, BASE_AI[0] | {"evaluation_finding_id": "a2"}],
    )
    assert next(item for item in result.matches if item.get("ground_truth_id"))["status"] == "UNCERTAIN"
