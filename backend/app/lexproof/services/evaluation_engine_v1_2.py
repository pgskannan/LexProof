"""Evaluator 1.2.0: isolated recommendation-quality comparator (Phase E.3-C).

Finding-matching (candidate generation, candidate gate, Hungarian global
assignment, tie/UNCERTAIN detection, MATCHED/MISSED/FALSE_POSITIVE status,
severity comparison, evidence grounding) is Evaluator 1.1.0's, completely
unchanged. This module does not reimplement, override, or otherwise touch a
single line of that logic: ``DeterministicEvaluationEngineV1_2.evaluate()``
calls ``super().evaluate(...)`` (i.e. ``DeterministicEvaluationEngineV1_1.
evaluate``) with the identical arguments and takes its returned matches
as-is. Only after that call does this module do anything at all, and even
then it only ever rewrites two fields -- ``recommendation_correct`` and the
new ``recommendation_similarity`` -- on the already-finished match records.
Every other field (``status``, ``category_match``, ``clause_match``,
``evidence_match``, ``numeric_match``, ``severity_correct``,
``evidence_grounding``, ``match_score`` ...) is whatever 1.1.0 produced,
untouched. Because ``_metrics()`` (inherited unchanged from
``evaluation_engine.py``) derives TP/FP/FN/UNCERTAIN and every metric other
than ``recommendation_accuracy`` purely from the ``status`` field (plus
``severity_correct``/``evidence_grounding``, also untouched), this
guarantees -- by construction, not merely by testing -- that
precision/recall/F1/severity_accuracy/critical_recall/high_risk_recall/
evidence_grounding and the TP/FP/FN/UNCERTAIN counts themselves are
byte-identical between 1.1.0 and 1.2.0 on any input. ``test_evaluation_
engine_v1_2.py`` proves this directly rather than just asserting it.

WHY ``_equal_signal`` WAS WRONG FOR THIS FIELD (Phase E.3-B's finding)
-----------------------------------------------------------------------
``_equal_signal`` (``evaluation_engine.py``) is exact-string-equality after
light normalization. It is the right tool for fields like
``finding_category`` or ``expected_severity``, which are drawn from a small
fixed vocabulary. A recommendation is free-form legal prose: two reviewers
(a human ground-truth author and an AI) essentially never produce the same
sentence for the same remedy, so ``_equal_signal`` returns ``False`` for
almost every real pair regardless of whether the AI's recommendation was
substantively correct -- which is exactly why ``recommendation_accuracy``
was 0.000 on every prior run. This module replaces only that one
comparison, for recommendation text specifically; it does not touch
``_equal_signal`` itself, which remains in use, unmodified, for every field
that still needs exact-vocabulary comparison (including inside 1.1.0's own
matching logic, which this module never re-executes with a different
comparator).

DESIGN NOTE 1 -- reuse investigated before writing anything new
-----------------------------------------------------------------------
Before designing a new comparator, the existing normalization/overlap
primitives already used elsewhere in the evaluator were investigated for
reuse: ``normalize_text``, ``text_tokens``, ``overlap_score`` (Jaccard),
``_STOP_WORDS`` (``evaluation_engine.py``), and 1.1.0's negation-polarity
machinery ``_all_tokens``/``_is_negated`` (``evaluation_engine_v1_1.py``).
``normalize_text``/``_STOP_WORDS`` are reused directly (imported, not
copied). ``_all_tokens``/``_is_negated`` are reused directly for the
conflict veto below. ``overlap_score`` (Jaccard) was tried first for the
similarity signal itself and rejected -- see Design Note 2. A new,
recommendation-specific generic-word list and a minimal synonym table were
added because the base engine's ``_STOP_WORDS`` (articles/prepositions)
does not cover legal-recommendation boilerplate ("clause", "require",
"provide", "agreement", "rights", ...), which is a different problem from
generic English stop words and is called out explicitly in the Phase E.3-C
brief as something that must not be credited as equivalence on its own.

DESIGN NOTE 2 -- overlap coefficient, not Jaccard
-----------------------------------------------------------------------
The first working version of this comparator used Jaccard similarity
(``overlap_score``'s formula, |A∩B|/|A∪B|) over content words and bigrams.
Run against the real 10 MATCHED Run #2 pairs (Phase E.3-B), this produced a
maximum similarity of 0.398 across ALL 10 pairs -- including the pair the
Phase E.3-C brief itself gives as a clear "should be judged correct"
example ("Add a clause allowing the Controller to update processing
instructions..." vs "Include a clause allowing the Controller to provide
documented instructions..."). Every threshold from 0.40 to 0.80 therefore
produced 0/10 "correct", reproducing the exact always-zero failure this
whole exercise exists to fix -- Jaccard's union-sized denominator is simply
too harsh for two independently-phrased sentences of different length.
Switching to the overlap (Szymkiewicz-Simpson) coefficient,
|A∩B| / min(|A|,|B|), fixes this: a short recommendation whose entire
content is contained in a longer, differently-phrased one now scores highly
on the *shorter* side's own terms rather than being diluted by the union.
This produced a stable bimodal separation on the real data (Design Note 5).

DESIGN NOTE 3 -- similarity formula
-----------------------------------------------------------------------
``recommendation_similarity(gt, ai)``:
  1. Tokenize both sides via the base engine's ``normalize_text``, then
     drop ``_STOP_WORDS`` (generic English) and the new
     ``_RECOMMENDATION_GENERIC_WORDS`` (domain boilerplate), keeping order
     for bigram construction. A minimal, explicitly-justified synonym
     canonicalization (Design Note 4) is folded in at normalization time.
  2. ``content_overlap`` = overlap coefficient of the two content-token
     sets. ``phrase_overlap`` = overlap coefficient of their bigram sets
     (rewards shared multi-word phrases like "fair market value", not just
     shared single words).
  3. ``similarity = 0.65 * content_overlap + 0.35 * phrase_overlap``,
     content-weighted because two short legal recommendations rarely share
     enough consecutive bigrams to carry the signal alone.
  4. A near-verbatim containment override: if one side's full normalized
     text is a substring of the other's, similarity is floored at 0.9 --
     this only ever raises a score that content/phrase overlap already
     placed close to it (containment implies high token overlap already),
     it never manufactures a spuriously high score from unrelated text.
  5. Returns ``None`` when either side is empty/whitespace-only, mirroring
     ``_equal_signal``'s own None convention -- ``_metrics()``'s existing
     "exclude None values from the ratio" handling for
     ``recommendation_accuracy`` therefore keeps working completely
     unchanged.
This is deliberately not a "huge legal ontology": one generic-word list,
one 4-entry synonym table (Design Note 4), and standard overlap/bigram
arithmetic -- every step is inspectable and explainable without a model.

DESIGN NOTE 4 -- synonym canonicalization (minimal, evidence-driven)
-----------------------------------------------------------------------
Two real Run #2 pairs (ground_truth_id 1b44ac5b and ef90449f) use
"reciprocal"/"reciprocally" on the ground-truth side against "mutual"/
"mutually" on the AI side for what a human reader would call the same
remedy. Neither token overlaps the other lexically, which is a genuine
false-negative source, not a hypothetical one. ``_RECOMMENDATION_SYNONYM_
CANON`` folds exactly these terms (plus "bilateral"/"bilaterally", the
same relationship) onto "mutual"/"mutually" during normalization. This is
one clearly-justified pair (plus its inflections), not a general thesaurus,
and it improved but did NOT flip either real pair's classification (see
Section 6 of the report) -- it makes the signal more honest, it does not
force an outcome.

DESIGN NOTE 5 -- avoiding overmatching: the conflict veto
-----------------------------------------------------------------------
Lexical similarity alone cannot tell "increase the cap" from "maintain the
cap" apart -- both share almost every content word. Tested directly against
the Phase E.3-C brief's own four adversarial examples, THREE of four
(mutual-vs-unilateral: sim=0.433; increase-vs-maintain: sim=0.608;
require-vs-prohibit: sim=0.442) score *above* the eventual 0.40 threshold on
pure lexical similarity and would be wrongly marked "correct" without an
explicit veto. ``recommendation_conflict(gt, ai)`` therefore checks, in
order:
  1. Aggregate negation polarity, reusing 1.1.0's own ``_all_tokens``/
     ``_is_negated`` unchanged (not reimplemented) -- disagreement means a
     genuine polarity reversal, not just "a negation word appears
     somewhere".
  2. A small, explicit list of domain contrast/antonym pairs
     (mutual/unilateral, increase/decrease, allow/prohibit, retain/remove,
     cap/unlimited, ...) drawn directly from the words the Phase E.3-C
     brief itself names as needing investigation.
  3. Materially different numbers: if both sides contain numeric tokens
     (``numeric_tokens``, reused unchanged from ``evaluation_engine.py``)
     and those number sets are completely disjoint, the recommendations are
     treated as prescribing different concrete remedies (e.g. "extend to
     30 days" vs "extend to 90 days") even though the surrounding prose is
     otherwise near-identical. This directly answers the brief's item 14
     (numbers/time periods materially differing): a pure lexical signal
     would score such a pair very highly (all the surrounding words match),
     so an explicit veto is necessary here for the same reason it is
     necessary for the antonym pairs. It does not fire when only one side
     states a number (most real ground-truth recommendations are phrased
     more abstractly than the AI's, e.g. "establish reasonable caps" vs "60
     days' notice" -- verified this never fires on any of the real 10
     Run #2 pairs; see the report).
``recommendation_correct(gt, ai)`` is ``None`` when either side is empty,
else ``similarity >= _RECOMMENDATION_MATCH_THRESHOLD and not conflict``.

DESIGN NOTE 6 -- threshold selection (data-driven, not chosen for effect)
-----------------------------------------------------------------------
See the Phase E.3-C report's Threshold Analysis section for the full
sensitivity table. Summary: computed against the real 10 Run #2 MATCHED
pairs, similarities fall into two clusters -- {0.460, 0.565, 0.573, 0.622}
(4 pairs) and {0.130, 0.153, 0.186, 0.212, 0.217, 0.259} (6 pairs) -- with a
stable gap of (0.259, 0.460]. Any threshold inside that gap (not only 0.40)
produces the identical 4/6 split, so 0.40 was picked as a round number
inside a wide, data-supported plateau rather than tuned to a preferred
count. ``_RECOMMENDATION_MATCH_THRESHOLD`` is the single named constant
controlling this; changing it does not require touching any other logic.
"""

from __future__ import annotations

from typing import Any

from .evaluation import EvaluationMatchStatus
from .evaluation_engine import (
    EvaluationResult,
    _STOP_WORDS,
    normalize_text,
    numeric_tokens,
)
from .evaluation_engine_v1_1 import (
    DeterministicEvaluationEngineV1_1,
    _all_tokens,
    _is_negated,
)

EVALUATOR_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Recommendation-specific vocabulary. Deliberately small and named exactly
# because it exists to satisfy an explicit requirement: shared generic words
# ("clause", "require", "provide", "add", "agreement", "rights", ...) must
# never by themselves be credited as substantive equivalence.
# ---------------------------------------------------------------------------
_RECOMMENDATION_GENERIC_WORDS = frozenset({
    "add", "adding", "clause", "clauses", "require", "requiring", "requires", "required",
    "provide", "providing", "provides", "provided", "agreement", "agreements",
    "right", "rights", "consider", "considering", "ensure", "ensuring",
    "include", "including", "included", "obligation", "obligations", "party", "parties",
    "should", "would", "could", "specify", "specifying", "establish", "establishing",
})

# One clearly-justified synonym relationship (plus inflections) motivated by
# two real observed false negatives (Design Note 4) -- not a general
# thesaurus.
_RECOMMENDATION_SYNONYM_CANON = {
    "reciprocal": "mutual",
    "reciprocally": "mutually",
    "bilateral": "mutual",
    "bilaterally": "mutually",
}

# Explicit directional/remedy-reversal contrast pairs (Design Note 5). Order
# within a pair does not matter -- both directions are checked.
_RECOMMENDATION_CONTRAST_PAIRS = (
    ("mutual", "unilateral"),
    ("mutually", "unilaterally"),
    ("increase", "decrease"),
    ("increase", "reduce"),
    ("increase", "maintain"),
    ("increasing", "decreasing"),
    ("decrease", "maintain"),
    ("reduce", "maintain"),
    ("allow", "prohibit"),
    ("allow", "remove"),
    ("permit", "prohibit"),
    ("require", "prohibit"),
    ("require", "remove"),
    ("retain", "remove"),
    ("retain", "eliminate"),
    ("cap", "unlimited"),
    ("capped", "uncapped"),
)

# See Design Note 6. The single knob controlling recommendation_correct.
_RECOMMENDATION_MATCH_THRESHOLD = 0.40


def _recommendation_normalize(value: Any) -> str:
    """``normalize_text`` (reused, unchanged) plus the minimal synonym fold
    from Design Note 4."""
    text = normalize_text(value)
    words = [_RECOMMENDATION_SYNONYM_CANON.get(word, word) for word in text.split()]
    return " ".join(words)


def _recommendation_content_tokens(value: Any) -> list[str]:
    """Ordered, de-genericized content tokens: drops the base engine's
    ``_STOP_WORDS`` (generic English) and this module's
    ``_RECOMMENDATION_GENERIC_WORDS`` (domain boilerplate)."""
    return [
        token
        for token in _recommendation_normalize(value).split()
        if token not in _STOP_WORDS and token not in _RECOMMENDATION_GENERIC_WORDS and len(token) > 1
    ]


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return {(tokens[index], tokens[index + 1]) for index in range(len(tokens) - 1)}


def _overlap_coefficient(left: set[Any], right: set[Any]) -> float:
    """|A∩B| / min(|A|,|B|). See Design Note 2 for why this, not Jaccard."""
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def recommendation_conflict(left: Any, right: Any) -> bool:
    """True only when the two recommendations appear to prescribe opposite
    or materially different remedies. See Design Note 5."""
    left_tokens = _all_tokens(left)
    right_tokens = _all_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if _is_negated(left_tokens) != _is_negated(right_tokens):
        return True
    for first, second in _RECOMMENDATION_CONTRAST_PAIRS:
        if (first in left_tokens and second in right_tokens) or (second in left_tokens and first in right_tokens):
            return True
    left_numbers = numeric_tokens(left)
    right_numbers = numeric_tokens(right)
    if left_numbers and right_numbers and left_numbers.isdisjoint(right_numbers):
        return True
    return False


def recommendation_similarity(left: Any, right: Any) -> float | None:
    """Deterministic (non-LLM) recommendation-similarity signal in [0, 1],
    or ``None`` when either side is empty. See Design Notes 2-3."""
    if not left or not right or not str(left).strip() or not str(right).strip():
        return None
    left_tokens = _recommendation_content_tokens(left)
    right_tokens = _recommendation_content_tokens(right)
    content_overlap = _overlap_coefficient(set(left_tokens), set(right_tokens))
    phrase_overlap = _overlap_coefficient(_bigrams(left_tokens), _bigrams(right_tokens))
    similarity = 0.65 * content_overlap + 0.35 * phrase_overlap
    left_norm = _recommendation_normalize(left)
    right_norm = _recommendation_normalize(right)
    if left_norm and right_norm and (left_norm in right_norm or right_norm in left_norm):
        similarity = max(similarity, 0.9)
    return min(1.0, similarity)


def recommendation_correct(left: Any, right: Any) -> bool | None:
    """``None`` when either side is empty (mirrors ``_equal_signal``);
    else a deterministic threshold-and-veto decision. See Design Notes 5-6."""
    similarity = recommendation_similarity(left, right)
    if similarity is None:
        return None
    return bool(similarity >= _RECOMMENDATION_MATCH_THRESHOLD and not recommendation_conflict(left, right))


class DeterministicEvaluationEngineV1_2(DeterministicEvaluationEngineV1_1):
    """Evaluator 1.2.0. See module docstring: matching is 1.1.0's,
    unmodified; only ``recommendation_correct``/``recommendation_similarity``
    are recomputed, as a post-processing pass over 1.1.0's own output."""

    evaluator_version = EVALUATOR_VERSION

    def evaluate(
        self,
        *,
        org_id: str,
        evaluation_run_id: str,
        dataset_version_id: str,
        ground_truth_findings,
        ai_findings,
        require_finalized: bool = True,
        evaluated_at=None,
    ) -> EvaluationResult:
        ground_truth = list(ground_truth_findings)
        ai = list(ai_findings)

        # Matching, gating, assignment, tie/status determination, severity
        # comparison, and evidence grounding are ENTIRELY 1.1.0's -- this is
        # a plain, unmodified call to the parent class's evaluate(), not a
        # reimplementation. See module docstring for why this guarantees
        # TP/FP/FN/UNCERTAIN invariance by construction.
        base_result = super().evaluate(
            org_id=org_id,
            evaluation_run_id=evaluation_run_id,
            dataset_version_id=dataset_version_id,
            ground_truth_findings=ground_truth,
            ai_findings=ai,
            require_finalized=require_finalized,
            evaluated_at=evaluated_at,
        )

        gt_by_id = {str(record["ground_truth_id"]): record for record in ground_truth if record.get("ground_truth_id")}
        ai_by_id = {str(record["evaluation_finding_id"]): record for record in ai if record.get("evaluation_finding_id")}

        matches: list[dict[str, Any]] = []
        for match in base_result.matches:
            updated = dict(match)
            gt_id = updated.get("ground_truth_id")
            ai_id = updated.get("evaluation_finding_id")
            if gt_id and ai_id:
                gt_item = gt_by_id.get(str(gt_id))
                ai_item = ai_by_id.get(str(ai_id))
                gt_rec = (gt_item or {}).get("expected_recommendation")
                ai_rec = (ai_item or {}).get("recommendation")
                updated["recommendation_similarity"] = recommendation_similarity(gt_rec, ai_rec)
                updated["recommendation_correct"] = recommendation_correct(gt_rec, ai_rec)
            else:
                # MISSED (no ai_id) or FALSE_POSITIVE (no gt_id): 1.1.0
                # already leaves recommendation_correct as None for these;
                # kept explicit here for clarity.
                updated["recommendation_similarity"] = None
                updated["recommendation_correct"] = None
            matches.append(updated)

        # _metrics() is inherited, unchanged, from evaluation_engine.py. It
        # reads TP/FP/FN/UNCERTAIN and every other metric from `status`
        # (untouched above); only recommendation_accuracy's inputs
        # (recommendation_correct on MATCHED-status records) differ from
        # 1.1.0's own run of the same matches.
        metrics = dict(self._metrics(org_id, evaluation_run_id, matches))

        # Additive graded diagnostic (Step 10): recommendation_accuracy
        # remains the binary ratio computed by the inherited _metrics(); this
        # adds the mean similarity over the same MATCHED-status population,
        # never replacing or altering the binary figure.
        detected_similarities = [
            item["recommendation_similarity"]
            for item in matches
            if item.get("status") == EvaluationMatchStatus.MATCHED.value and item.get("recommendation_similarity") is not None
        ]
        metrics["recommendation_similarity_avg"] = (
            sum(detected_similarities) / len(detected_similarities) if detected_similarities else None
        )
        metrics["recommendation_similarity_count"] = len(detected_similarities)

        return EvaluationResult(matches=matches, metrics=metrics)
