"""Deterministic tests for Evaluator 1.2.0 (Phase E.3-C).

Two things this file must prove, per the Phase E.3-C brief:

1. INVARIANCE: on the same input, 1.2.0 produces byte-identical
   TP/FP/FN/UNCERTAIN counts (and every metric derived purely from
   ``status``/``severity_correct``/``evidence_grounding``) to 1.1.0. This is
   guaranteed by construction (1.2.0's evaluate() calls 1.1.0's evaluate()
   unmodified -- see evaluation_engine_v1_2.py's module docstring), and the
   tests below exercise that guarantee directly rather than merely trusting
   the construction argument.
2. The recommendation comparator itself: the 14 adversarial cases the brief
   requires, plus a regression check against the real 10 Run #2 MATCHED
   pairs' actual recommendation text (Phase E.3-B), so a future change to
   this file cannot silently drift the real-data classification without a
   test failing.

Nothing here calls Firestore, an AI provider, or persists anything -- pure
in-memory fixtures, same convention as test_evaluation_engine_v1_1.py.
"""

from __future__ import annotations

import pytest

from app.lexproof.services.evaluation_engine_v1_1 import DeterministicEvaluationEngineV1_1
from app.lexproof.services.evaluation_engine_v1_2 import (
    DeterministicEvaluationEngineV1_2,
    _RECOMMENDATION_MATCH_THRESHOLD,
    recommendation_conflict,
    recommendation_correct,
    recommendation_similarity,
)

ORG_ID = "org-1"
RUN_ID = "run-1"
DATASET_ID = "dataset-v1"


def gt(gt_id, category, clause, severity, finding, evidence, recommendation="Review the clause.", contract_id="contract-1", version_id="version-1"):
    return {
        "ground_truth_id": gt_id,
        "org_id": ORG_ID,
        "dataset_version_id": DATASET_ID,
        "contract_id": contract_id,
        "version_id": version_id,
        "finding_category": category,
        "clause_reference": clause,
        "expected_severity": severity,
        "expected_finding": finding,
        "expected_evidence": evidence,
        "expected_recommendation": recommendation,
        "review_status": "FINALIZED",
    }


def ai(ai_id, category, clause, severity, finding, evidence, recommendation="Review the clause.", contract_id="contract-1", version_id="version-1"):
    return {
        "evaluation_finding_id": ai_id,
        "org_id": ORG_ID,
        "dataset_version_id": DATASET_ID,
        "evaluation_run_id": RUN_ID,
        "contract_id": contract_id,
        "version_id": version_id,
        "finding_category": category,
        "clause_reference": clause,
        "severity": severity,
        "finding": finding,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def evaluate(ground_truth, ai_findings, engine_cls=DeterministicEvaluationEngineV1_2):
    return engine_cls().evaluate(
        org_id=ORG_ID,
        evaluation_run_id=RUN_ID,
        dataset_version_id=DATASET_ID,
        ground_truth_findings=ground_truth,
        ai_findings=ai_findings,
    )


def gt_match(result, gt_id):
    return next(item for item in result.matches if item.get("ground_truth_id") == gt_id)


# ---------------------------------------------------------------------------
# INVARIANCE: 1.2.0 must reproduce 1.1.0's matching exactly.
# ---------------------------------------------------------------------------

_INVARIANCE_GROUND_TRUTH = [
    gt("g1", "One-Sided Indemnification", "Section 8", "HIGH",
       "The indemnification obligation runs only in favor of the vendor.",
       "Customer shall indemnify, defend, and hold harmless Vendor from any and all claims.",
       recommendation="Require mutual consent for assignment or provide equivalent assignment rights."),
    gt("g2", "Data Retention", "Section 5", "MEDIUM",
       "Retention period is undefined", "Data shall be retained for an unspecified period",
       recommendation="Consider extending the confidentiality survival period."),
    gt("g3", "Fee Increases", "Section 3", "HIGH",
       "Fee increases are unilateral", "Vendor may increase fees at its sole discretion",
       recommendation="Require mutual written agreement for fee increases."),
]
_INVARIANCE_AI_FINDINGS = [
    ai("a1", "Indemnification", "Section 8", "HIGH",
       "Indemnification obligations are one-sided in favor of the vendor.",
       "Customer shall indemnify, defend, and hold harmless Vendor from any and all claims.",
       recommendation="Make assignment rights mutual, requiring consent for any change of control."),
    ai("a2", "Termination Rights", "Section 11", "HIGH",
       "Either party may terminate for convenience",
       "Either party may terminate this Agreement for convenience upon 30 days notice",
       recommendation="Add a termination-for-convenience clause with a 30 day notice period."),
]


def test_invariance_status_counts_are_identical_to_1_1_0():
    """Same input, two different evaluator instances: TP/FP/FN/UNCERTAIN
    counts must match exactly (Phase E.3-C, Step 5)."""
    result_1_1 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_1)
    result_1_2 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_2)

    def counts(result):
        return {
            "MATCHED": sum(item["status"] == "MATCHED" for item in result.matches),
            "MISSED": sum(item["status"] == "MISSED" for item in result.matches),
            "FALSE_POSITIVE": sum(item["status"] == "FALSE_POSITIVE" for item in result.matches),
            "UNCERTAIN": sum(item["status"] == "UNCERTAIN" for item in result.matches),
        }

    assert counts(result_1_1) == counts(result_1_2)
    assert result_1_1.metrics["true_positives"] == result_1_2.metrics["true_positives"]
    assert result_1_1.metrics["false_positives"] == result_1_2.metrics["false_positives"]
    assert result_1_1.metrics["false_negatives"] == result_1_2.metrics["false_negatives"]
    assert result_1_1.metrics["uncertain_count"] == result_1_2.metrics["uncertain_count"]


def test_invariance_every_non_recommendation_field_is_identical_per_match():
    """Per-match fields other than recommendation_correct/
    recommendation_similarity must be pairwise identical between engines."""
    result_1_1 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_1)
    result_1_2 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_2)
    ignore = {"recommendation_correct", "recommendation_similarity", "evaluator_version", "evaluation_match_id", "created_at"}

    by_key_1_1 = {(m.get("ground_truth_id"), m.get("evaluation_finding_id")): m for m in result_1_1.matches}
    by_key_1_2 = {(m.get("ground_truth_id"), m.get("evaluation_finding_id")): m for m in result_1_2.matches}
    assert set(by_key_1_1) == set(by_key_1_2)
    for key, match_1_1 in by_key_1_1.items():
        match_1_2 = by_key_1_2[key]
        for field in match_1_1:
            if field in ignore:
                continue
            assert match_1_1[field] == match_1_2[field], f"field {field!r} differs for {key}"


def test_invariance_metrics_other_than_recommendation_are_identical():
    result_1_1 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_1)
    result_1_2 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_2)
    ignore = {"recommendation_accuracy", "evaluator_version", "evaluation_metrics_id", "recommendation_similarity_avg", "recommendation_similarity_count"}
    for key in result_1_1.metrics:
        if key in ignore:
            continue
        assert result_1_1.metrics[key] == result_1_2.metrics[key], f"metric {key!r} differs"


def test_1_2_0_adds_new_fields_without_removing_any_1_1_0_field():
    result_1_1 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_1)
    result_1_2 = evaluate(_INVARIANCE_GROUND_TRUTH, _INVARIANCE_AI_FINDINGS, engine_cls=DeterministicEvaluationEngineV1_2)
    assert set(result_1_1.metrics) <= set(result_1_2.metrics)
    assert "recommendation_similarity_avg" in result_1_2.metrics
    assert "recommendation_similarity_count" in result_1_2.metrics
    for match in result_1_2.matches:
        assert "recommendation_similarity" in match


# ---------------------------------------------------------------------------
# 14 required adversarial cases for the recommendation comparator itself.
# ---------------------------------------------------------------------------


def test_case_01_exact_same_text_is_correct():
    text = "Require mutual written consent before either party may assign this Agreement."
    assert recommendation_correct(text, text) is True
    assert recommendation_similarity(text, text) == 1.0


def test_case_02_case_and_punctuation_variation_is_correct():
    left = "Require mutual written consent before either party may assign this Agreement."
    right = "require MUTUAL, written consent before either party may assign this agreement"
    assert recommendation_correct(left, right) is True


def test_case_03_strong_paraphrase_is_correct():
    left = "Add a clause allowing the Controller to update processing instructions in writing at any time, with the Processor obligated to comply."
    right = "Include a clause allowing the Controller to provide documented instructions at any time and requiring the Processor to comply with such instructions."
    assert recommendation_correct(left, right) is True


def test_case_04_same_remedy_different_wording_is_correct():
    left = "Align revenue share with ownership percentages or provide justification and compensation for the imbalance."
    right = "Align revenue distribution with equity ownership percentages."
    assert recommendation_correct(left, right) is True


def test_case_05_same_subject_opposite_remedy_is_incorrect():
    left = "Require mutual consent for assignment."
    right = "Allow unilateral assignment without consent."
    assert recommendation_conflict(left, right) is True
    assert recommendation_correct(left, right) is False


def test_case_06_mutual_vs_unilateral_is_incorrect():
    left = "Require mutual consent for assignment or provide Orion with equivalent assignment rights."
    right = "Make assignment rights mutual, requiring consent for any change of control."
    # Sanity: this specific pair is one of the real Run #2 pairs and is NOT
    # a conflict (both say "mutual") -- the true adversarial case is the
    # unilateral variant:
    unilateral_right = "Allow either party to assign this Agreement unilaterally without the other's consent."
    assert recommendation_conflict(left, unilateral_right) is True
    assert recommendation_correct(left, unilateral_right) is False
    assert recommendation_conflict(left, right) is False


def test_case_07_increase_vs_decrease_is_incorrect():
    left = "Increase the liability cap to a commercially reasonable multiple of fees paid."
    right = "Decrease the liability cap to a lower, fixed dollar amount."
    assert recommendation_conflict(left, right) is True
    assert recommendation_correct(left, right) is False


def test_case_08_require_vs_prohibit_is_incorrect():
    left = "Require written notice before any subcontracting arrangement."
    right = "Prohibit written notice requirements before any subcontracting arrangement."
    assert recommendation_conflict(left, right) is True
    assert recommendation_correct(left, right) is False


def test_case_09_completely_unrelated_is_incorrect():
    left = "Extend the confidentiality survival period to five years."
    right = "Add a governing law clause specifying New York law."
    assert recommendation_correct(left, right) is False


def test_case_10_empty_ground_truth_is_none():
    assert recommendation_similarity("", "Extend the survival period.") is None
    assert recommendation_correct(None, "Extend the survival period.") is None


def test_case_11_empty_ai_is_none():
    assert recommendation_similarity("Extend the survival period.", "") is None
    assert recommendation_correct("Extend the survival period.", None) is None


def test_case_12_both_empty_is_none():
    assert recommendation_similarity("", "") is None
    assert recommendation_similarity(None, None) is None
    assert recommendation_correct("", "") is None


def test_case_13_generic_shared_words_alone_do_not_match():
    """Every word in both sentences is either a generic English stop word
    or in _RECOMMENDATION_GENERIC_WORDS -- there is zero substantive
    content overlap, so this must not match despite reading, superficially,
    like two paraphrases of the same instruction."""
    left = "The parties should add a clause to require and provide rights and obligations for the agreement."
    right = "The party could add a clause to require and provide obligations and rights for the agreements."
    similarity = recommendation_similarity(left, right)
    assert similarity is not None
    assert similarity == 0.0
    assert similarity < _RECOMMENDATION_MATCH_THRESHOLD
    assert recommendation_correct(left, right) is False


def test_case_14_materially_different_numbers_are_incorrect_despite_high_lexical_overlap():
    left = "Extend the cure period to 30 days to align with industry practice."
    right = "Extend the cure period to 90 days to align with industry practice."
    similarity = recommendation_similarity(left, right)
    # Lexical overlap alone is very high (only the number differs) -- this is
    # exactly why the numeric-disjoint veto in recommendation_conflict exists.
    assert similarity is not None and similarity >= _RECOMMENDATION_MATCH_THRESHOLD
    assert recommendation_conflict(left, right) is True
    assert recommendation_correct(left, right) is False


def test_case_14b_same_number_on_both_sides_does_not_trigger_numeric_veto():
    left = "Extend the cure period to 30 days to align with industry practice."
    right = "Extend the cure period to 30 days to align with industry practice, per standard terms."
    assert recommendation_conflict(left, right) is False


def test_case_14c_number_on_only_one_side_does_not_trigger_numeric_veto():
    left = "Establish reasonable caps or limits on the fee increase."
    right = "Require at least 60 days' notice before any fee increase takes effect."
    assert recommendation_conflict(left, right) is False


# ---------------------------------------------------------------------------
# Regression check against the real 10 Run #2 MATCHED pairs (Phase E.3-B).
# These are the actual expected_recommendation / recommendation strings read
# from Firestore during Phase E.3-B; embedding them here as plain string
# literals is not a Firestore call and persists nothing -- it just prevents
# a future change to this module from silently changing the real-data
# classification without a test noticing.
# ---------------------------------------------------------------------------

_REAL_RUN_2_PAIRS = [
    ("1b44ac5b", "Grant reciprocal rights or restrict Meridian's use of JV IP outside the JV unless mutually agreed.",
     "Ensure IP rights are mutual, particularly regarding improvements or learnings derived from the JV Platform.", False),
    ("4fd7d075", "Add a clause allowing the Controller to update processing instructions in writing at any time, with the Processor obligated to comply.",
     "Include a clause allowing the Controller to provide documented instructions at any time and requiring the Processor to comply with such instructions.", True),
    ("56d03930", "Require mutual written agreement for fee increases, or establish reasonable caps/limits and an explicit termination right if the customer does not accept the increase.",
     "Require at least 60 days' notice and provide Customer the right to terminate if they do not accept the price increase.", False),
    ("7e11912e", "Provide joint ownership of JV IP or require fair market value compensation for Orion's share.",
     "Provide for joint ownership or a fair market value buyout of IP upon dissolution.", True),
    ("aa6327ec", "Specify a fair, mutually agreed dilution formula or require independent valuation rather than unilateral determination.",
     "Replace with a standard, pre-defined dilution formula or a mandatory mediation process for capital call disputes.", False),
    ("b0dafaed", "Require mutual consent for assignment or provide Orion with equivalent assignment rights.",
     "Make assignment rights mutual, requiring consent for any change of control.", True),
    ("dc23086b", "Consider extending the confidentiality survival period, particularly for sensitive information and trade secrets.",
     "Extend the survival period to 3-5 years to align with standard industry practices.", False),
    ("de1b1162", "Align revenue share with ownership percentages or provide justification and compensation for the imbalance.",
     "Align revenue distribution with equity ownership percentages.", True),
    ("e6e066b6", "Add SLA timelines and procedures for Processor assistance with access, erasure, rectification, and portability requests.",
     "Add a provision requiring the Processor to assist the Controller by appropriate technical and organizational measures for the fulfillment of the Controller's obligation to respond to requests for exercising data subject rights.", False),
    ("ef90449f", "Add reciprocal exclusivity obligations or limit Orion's exclusivity to the JV term only.",
     "Make non-compete and exclusivity obligations mutual and time-bound to a reasonable duration (e.g., 12 months).", False),
]


@pytest.mark.parametrize("gt_id,gt_rec,ai_rec,expect_correct", _REAL_RUN_2_PAIRS)
def test_real_run_2_pairs_classification_is_stable(gt_id, gt_rec, ai_rec, expect_correct):
    assert recommendation_correct(gt_rec, ai_rec) is expect_correct, gt_id


def test_real_run_2_pairs_none_are_flagged_as_conflicts():
    """None of the real 10 pairs involve an actual directional reversal or
    disjoint numeric remedy -- the veto exists for the adversarial cases
    above, not because any real pair needed it."""
    for gt_id, gt_rec, ai_rec, _expect_correct in _REAL_RUN_2_PAIRS:
        assert recommendation_conflict(gt_rec, ai_rec) is False, gt_id
