"""Evaluator 1.1.0: fairer semantic-correspondence matching (Phase E.2).

Evaluator 1.0.0 (``evaluation_engine.py``) is now historical/frozen. Nothing
in this module edits its behavior, imports it destructively, or changes its
outputs; this is a separate, independently callable engine that happens to
reuse 1.0.0's proven, unchanged primitives (text normalization, overlap
scoring, evidence grounding, metrics aggregation, record shaping) via plain
subclassing.

Phase E.1's forensic audit found that zero true-positives on the frozen
baseline run was caused mostly by evaluator taxonomy/matching behavior, not
solely by AI coverage gaps. This module fixes exactly the mechanisms that
were identified, and nothing else:

1. CATEGORY IS A WEIGHTED SIGNAL, NOT A GATE
   ``category_match`` is still computed and still reported (True / False /
   None) as an observable signal, but it now contributes a small, fixed
   weight to the composite score (see ``_WEIGHT_CATEGORY`` below) instead of
   being a hard prerequisite. A finding can still be MATCHED when category
   labels differ entirely, provided clause and evidence corroborate it.
   No individual category-label pair (e.g. "Payment Terms" vs "Unilateral
   Fee Increase") is special-cased; the mechanism is general.

2. DETERMINISTIC CLAUSE NORMALIZATION
   ``normalize_clause`` strips a leading legal-reference label ("Section",
   "§", "Article", "Clause", ...) and, when a numeric identifier follows,
   uses that identifier alone as the canonical key. "Section 3.1" and
   "§3.1 Fees" both normalize to "3.1". Subsections remain distinct:
   "Section 7" -> "7", "Section 7.1" -> "7.1" (not equal). When there is no
   leading number, the full normalized text is kept -- meaningful text is
   never simply discarded.

3. PHRASE-AWARE, CONSERVATIVE SEMANTIC-CONFLICT CHECK
   The 1.0.0 heuristic flagged a conflict whenever a bare negation token
   ("not", "no") appeared on only one side, which incorrectly flagged
   "does not define" against "fails to define" as contradictory even though
   both are negative phrasings of the same statement. 1.1.0 first computes
   an aggregate "is this phrase negated at all" signal from a broader marker
   set (not/no/never/without/cannot/fails/failure/unable/lacks/lacking) and
   only flags a conflict when that aggregate disagrees between the two
   sides. A short list of explicit antonym/contrast pairs (excluded vs
   included, prohibited vs permitted, cause vs convenience) is preserved
   from 1.0.0 as an independent, additional conflict signal.

4. CANDIDATE GATE LETS STRONG EVIDENCE SURVIVE A CATEGORY MISMATCH
   See ``_passes_candidate_gate`` and its module docstring for the exact,
   documented policy and the reasoning behind each branch.

5. GLOBAL MAXIMUM-WEIGHT ONE-TO-ONE ASSIGNMENT
   1.0.0 assigns matches by sorting all candidate pairs by score and taking
   them greedily (first-fit). That is provably not always optimal: taking
   the single highest-scoring pair can block a strictly better *total*
   assignment elsewhere (see the assignment tests for a constructed
   counterexample). 1.1.0 computes a true global maximum-weight one-to-one
   assignment per (contract_id, version_id) group with the classical
   O(n^3) Hungarian algorithm (``_hungarian_assign``), padded with
   zero-cost "leave unassigned" dummy slots on both sides so a *partial*
   matching (not every item need be matched) is still found exactly.

6. SEVERITY NEVER GATES MATCH STATUS
   This was already true in 1.0.0 (severity only ever affected
   ``severity_correct``, a separate metric) and remains true here; 1.1.0
   does not change the meaning of severity_accuracy, critical_recall, or
   high_risk_recall.

7. STATUS DECISION ORDER (``_determine_status``), most conservative first:
   a. A genuine local ambiguity (two candidates tied on score with
      materially different signals) -> UNCERTAIN.
   b. A genuine semantic polarity conflict between the finding texts ->
      UNCERTAIN (never silently matched).
   c. A genuine numeric conflict (different numbers appear on each side) ->
      UNCERTAIN.
   d. Otherwise: MATCHED if the composite score clears
      ``_MATCH_SCORE_THRESHOLD`` *and* at least one concrete, checkable
      signal corroborates it (evidence overlap, finding-text overlap, or a
      normalized clause match) -- category and severity are deliberately
      absent from this final check.
   e. Otherwise -> UNCERTAIN.
   Nothing here was tuned against the specific 12 stored AI findings or the
   29 ground-truth records; every threshold is a round, general number
   chosen from the adversarial unit tests in ``test_evaluation_engine_v1_1.py``,
   before this engine was ever run against the frozen baseline (see the
   Phase E.2 report's benchmark-integrity section).
"""

from __future__ import annotations

import re
from typing import Any

from .evaluation import (
    EvaluationError,
    EvaluationMatchStatus,
    EvaluationStatus,
)
from .evaluation_engine import (
    DeterministicEvaluationEngine,
    EvaluationResult,
    _STABLE_EVALUATION_TIME,
    _UNKNOWN,
    _candidate_fingerprint,
    _equal_signal,
    _evidence_grounding,
    _evidence_text,
    _finding_text,
    normalize_text,
    numeric_tokens,
    overlap_score,
    text_tokens,
)

EVALUATOR_VERSION = "1.1.0"

# ---------------------------------------------------------------------------
# Composite-score weights. Evidence and finding-text overlap carry the bulk
# of the weight (70% combined) precisely so that a category disagreement
# (10% weight) can never by itself prevent a match, and so that a clause
# disagreement (20% weight) can be outweighed by strong evidence.
# ---------------------------------------------------------------------------
_WEIGHT_EVIDENCE = 0.40
_WEIGHT_FINDING = 0.30
_WEIGHT_CLAUSE = 0.20
_WEIGHT_CATEGORY = 0.10

# Candidate-gate and status thresholds. See _passes_candidate_gate and
# _determine_status for how each is used.
_EVIDENCE_STRONG = 0.5
_FINDING_CONFIRM = 0.5
_CLAUSE_CORROBORATION_EVIDENCE = 0.2
_CLAUSE_CORROBORATION_FINDING = 0.4
_FINDING_STRONG = 0.75
_FINDING_STRONG_EVIDENCE_FLOOR = 0.35
_MATCH_SCORE_THRESHOLD = 0.55


# ---------------------------------------------------------------------------
# 2. Clause normalization
# ---------------------------------------------------------------------------

_CLAUSE_LABEL = re.compile(r"^\s*(?:§+|section|sec\.?|article|art\.?|clause|cl\.?)\s*", re.IGNORECASE)
_LEADING_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\b")


def normalize_clause(value: Any) -> str:
    """Canonical clause key: leading numeric identifier if present, else the
    full normalized text. See the module docstring, item 2, for examples."""
    text = str(value or "").strip()
    if not text:
        return ""
    stripped = _CLAUSE_LABEL.sub("", text).strip()
    match = _LEADING_NUMBER.match(stripped)
    if match:
        return match.group(1)
    return normalize_text(stripped)


def _clause_signal(left: Any, right: Any) -> bool | None:
    left_norm = normalize_clause(left)
    right_norm = normalize_clause(right)
    if not left_norm or not right_norm:
        return None
    return left_norm == right_norm


# ---------------------------------------------------------------------------
# 3. Semantic conflict: phrase-aware, conservative
# ---------------------------------------------------------------------------

_NEGATION_MARKERS = {
    "not", "no", "never", "without", "cannot", "fails", "failure", "unable", "lacks", "lacking", "nor",
}
_CONTRAST_PAIRS = (("excluded", "included"), ("prohibited", "permitted"), ("cause", "convenience"))


def _all_tokens(value: Any) -> set[str]:
    return text_tokens(value) | set(normalize_text(value).split())


def _is_negated(tokens: set[str]) -> bool:
    return any(marker in tokens for marker in _NEGATION_MARKERS)


def semantic_conflict(left: Any, right: Any) -> bool:
    """True only for a genuine polarity/meaning reversal.

    Two different ways of expressing the *same* negative ("does not
    define" vs "fails to define") must NOT be flagged -- both sides are
    negated, so the aggregate polarity agrees. A true reversal ("does not
    permit" vs "permits") disagrees on that aggregate and is flagged. A
    short, explicit list of contrast pairs is checked independently of
    negation polarity (e.g. "prohibited" vs "permitted", neither of which
    is itself a negation-marker token).
    """
    left_tokens = _all_tokens(left)
    right_tokens = _all_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if _is_negated(left_tokens) != _is_negated(right_tokens):
        return True
    for first, second in _CONTRAST_PAIRS:
        if (first in left_tokens and second in right_tokens) or (second in left_tokens and first in right_tokens):
            return True
    return False


# ---------------------------------------------------------------------------
# 4. Candidate gate
#
# Policy (documented, general -- no per-example special cases):
#   (a) Evidence overlap alone is decisive if it is strong (>= 0.5): a
#       near-verbatim quoted match is trustworthy corroboration regardless
#       of what the category or clause labels say.
#   (b) A normalized clause match plus *some* other corroboration (weak
#       evidence overlap or weak finding-text overlap) is enough -- this is
#       the case a differently-worded category label (e.g. "One-Sided
#       Indemnification" vs "Indemnification") should not be able to block.
#   (c) Category and clause both agreeing structurally (the 1.0.0 "easy"
#       case) always survives.
#   (d) Very high finding-text similarity (>= 0.75) plus a moderate evidence
#       floor (>= 0.35) survives even with no clause or category agreement
#       at all -- but a *bare* high finding-text overlap with only weak
#       evidence (e.g. two findings that happen to reuse the same short
#       boilerplate phrase, like "limitation of liability", about otherwise
#       unrelated clauses) does NOT survive on its own; this prevents the
#       gate from being trivially gamed by generic phrase reuse.
# ---------------------------------------------------------------------------


def _passes_candidate_gate(signals: dict[str, Any]) -> bool:
    evidence_score = signals.get("evidence_score", 0.0)
    finding_score = signals.get("finding_score", 0.0)
    clause_match = signals.get("clause_match")
    category_match = signals.get("category_match")
    if evidence_score >= _EVIDENCE_STRONG:
        return True
    if clause_match is True and (evidence_score >= _CLAUSE_CORROBORATION_EVIDENCE or finding_score >= _CLAUSE_CORROBORATION_FINDING):
        return True
    if category_match is True and clause_match is True:
        return True
    if finding_score >= _FINDING_STRONG and evidence_score >= _FINDING_STRONG_EVIDENCE_FLOOR:
        return True
    return False


# ---------------------------------------------------------------------------
# 5. Global one-to-one assignment: classical Hungarian algorithm (O(n^3)),
# square-padded with zero-cost dummy slots so a partial matching is exact.
# ---------------------------------------------------------------------------

_DISALLOWED_COST = 10.0  # strictly worse than any real (0..1) or dummy (0) option


def _hungarian_assign(gt_ids: list[str], ai_ids: list[str], score_lookup: dict[tuple[str, str], float]) -> dict[str, str]:
    """Deterministic global maximum-weight one-to-one assignment.

    ``gt_ids`` and ``ai_ids`` must each be pre-sorted by the caller so the
    result never depends on input/iteration order. Only pairs present in
    ``score_lookup`` are eligible; everything else is padded with
    zero-cost "leave unassigned" slots on both sides, so this always finds
    the true optimal *partial* matching, not a forced perfect one.
    """
    m = len(gt_ids)
    n = len(ai_ids)
    if m == 0 or n == 0:
        return {}
    size = m + n
    cost = [[0.0] * size for _ in range(size)]
    for i, gt_id in enumerate(gt_ids):
        for j, ai_id in enumerate(ai_ids):
            score = score_lookup.get((gt_id, ai_id))
            cost[i][j] = -score if score is not None else _DISALLOWED_COST

    inf = float("inf")
    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    p = [0] * (size + 1)
    way = [0] * (size + 1)

    for i in range(1, size + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = -1
            for j in range(1, size + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(size + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    row_to_col: list[int | None] = [None] * size
    for j in range(1, size + 1):
        if p[j] != 0:
            row_to_col[p[j] - 1] = j - 1

    assigned: dict[str, str] = {}
    for i, gt_id in enumerate(gt_ids):
        j = row_to_col[i]
        if j is not None and j < n:
            ai_id = ai_ids[j]
            if (gt_id, ai_id) in score_lookup:
                assigned[gt_id] = ai_id
    return assigned


def _total_score(assignment: dict[str, str], score_lookup: dict[tuple[str, str], float]) -> float:
    """Sum of the assigned pairs' scores -- used by tests to prove
    optimality, and available to callers that want to report it."""
    return sum(score_lookup[(gt_id, ai_id)] for gt_id, ai_id in assignment.items())


def greedy_assign(gt_ids: list[str], ai_ids: list[str], score_lookup: dict[tuple[str, str], float]) -> dict[str, str]:
    """Score-sorted greedy first-fit assignment -- 1.0.0's algorithm,
    reimplemented standalone (not imported from evaluation_engine.py, which
    is frozen) purely so tests can prove global assignment dominates it."""
    pairs = sorted(score_lookup.items(), key=lambda row: (-row[1], row[0][0], row[0][1]))
    used_gt: set[str] = set()
    used_ai: set[str] = set()
    assigned: dict[str, str] = {}
    for (gt_id, ai_id), _score in pairs:
        if gt_id in used_gt or ai_id in used_ai:
            continue
        assigned[gt_id] = ai_id
        used_gt.add(gt_id)
        used_ai.add(ai_id)
    return assigned


class DeterministicEvaluationEngineV1_1(DeterministicEvaluationEngine):
    """Evaluator 1.1.0. See module docstring for the full design rationale."""

    evaluator_version = EVALUATOR_VERSION

    def _candidate_score(self, ground_truth: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
        category_match = _equal_signal(ground_truth.get("finding_category"), ai.get("finding_category") or ai.get("clause_type"))
        clause_match = _clause_signal(ground_truth.get("clause_reference"), ai.get("clause_reference") or ai.get("source_section"))
        evidence_score = overlap_score(ground_truth.get("expected_evidence"), _evidence_text(ai, ground_truth=False))
        finding_score = overlap_score(_finding_text(ground_truth, ground_truth=True), _finding_text(ai, ground_truth=False))
        evidence_match = evidence_score >= 0.5 if ground_truth.get("expected_evidence") and _evidence_text(ai, ground_truth=False) else None
        severity_match = _equal_signal(ground_truth.get("expected_severity"), ai.get("severity"))
        expected_numbers = numeric_tokens(_finding_text(ground_truth, ground_truth=True) + " " + str(ground_truth.get("expected_evidence") or ""))
        actual_numbers = numeric_tokens(_finding_text(ai, ground_truth=False) + " " + _evidence_text(ai, ground_truth=False))
        numeric_match = expected_numbers == actual_numbers if expected_numbers and actual_numbers else None
        semantic_match = not semantic_conflict(_finding_text(ground_truth, ground_truth=True), _finding_text(ai, ground_truth=False))
        category_component = 1.0 if category_match else (0.5 if category_match is None else 0.0)
        clause_component = 1.0 if clause_match else (0.5 if clause_match is None else 0.0)
        score = (
            _WEIGHT_EVIDENCE * evidence_score
            + _WEIGHT_FINDING * finding_score
            + _WEIGHT_CLAUSE * clause_component
            + _WEIGHT_CATEGORY * category_component
        )
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

    def _determine_status(self, signals: dict[str, Any], tied: bool) -> EvaluationMatchStatus:
        if tied:
            return EvaluationMatchStatus.UNCERTAIN
        if signals.get("semantic_match") is False:
            return EvaluationMatchStatus.UNCERTAIN
        if signals.get("numeric_match") is False:
            return EvaluationMatchStatus.UNCERTAIN
        if signals["score"] >= _MATCH_SCORE_THRESHOLD and (
            signals["evidence_score"] >= _EVIDENCE_STRONG
            or signals["finding_score"] >= _FINDING_CONFIRM
            or signals.get("clause_match") is True
        ):
            return EvaluationMatchStatus.MATCHED
        return EvaluationMatchStatus.UNCERTAIN

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
        if require_finalized and any(record.get("review_status") != EvaluationStatus.FINALIZED.value for record in ground_truth):
            raise EvaluationError("Evaluation requires finalized ground-truth findings")
        if any(record.get("org_id") != org_id for record in [*ground_truth, *ai]):
            raise EvaluationError("Evaluation records must belong to the active organization")

        # Matches only ever occur within the same (contract_id, version_id)
        # group, exactly as in 1.0.0; each group's assignment problem is
        # solved independently.
        groups: dict[tuple[str, str], dict[str, list]] = {}
        for gt_item in ground_truth:
            key = (gt_item.get("contract_id"), gt_item.get("version_id"))
            groups.setdefault(key, {"gt": [], "ai": []})["gt"].append(gt_item)
        for item in ai:
            key = (item.get("contract_id"), item.get("version_id"))
            groups.setdefault(key, {"gt": [], "ai": []})["ai"].append(item)

        signals_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
        score_by_pair: dict[tuple[str, str], float] = {}
        assigned: dict[str, str] = {}

        for _key, bucket in groups.items():
            gt_bucket = bucket["gt"]
            ai_bucket = bucket["ai"]
            candidate_gt_ids: list[str] = []
            candidate_ai_ids: list[str] = []
            seen_gt: set[str] = set()
            seen_ai: set[str] = set()
            for gt_item in gt_bucket:
                gt_id = str(gt_item["ground_truth_id"])
                for item in ai_bucket:
                    ai_id = str(item["evaluation_finding_id"])
                    signals = self._candidate_score(gt_item, item)
                    if not _passes_candidate_gate(signals):
                        continue
                    signals_by_pair[(gt_id, ai_id)] = signals
                    score_by_pair[(gt_id, ai_id)] = signals["score"]
                    if gt_id not in seen_gt:
                        seen_gt.add(gt_id)
                        candidate_gt_ids.append(gt_id)
                    if ai_id not in seen_ai:
                        seen_ai.add(ai_id)
                        candidate_ai_ids.append(ai_id)
            if candidate_gt_ids and candidate_ai_ids:
                assigned.update(_hungarian_assign(sorted(candidate_gt_ids), sorted(candidate_ai_ids), score_by_pair))

        # Local-ambiguity ("tied") detection: a ground-truth finding is tied
        # when, among its own surviving candidates, more than one AI finding
        # shares the top score with a materially different signal
        # fingerprint. This mirrors 1.0.0's tie concept but is evaluated
        # against each ground-truth finding's own candidate set rather than
        # the single global greedy frontier, since assignment here is no
        # longer a single sorted frontier.
        tied_gt: set[str] = set()
        for _key, bucket in groups.items():
            for gt_item in bucket["gt"]:
                gt_id = str(gt_item["ground_truth_id"])
                options = [
                    (score_by_pair[(gt_id, str(item["evaluation_finding_id"]))], signals_by_pair[(gt_id, str(item["evaluation_finding_id"]))])
                    for item in bucket["ai"]
                    if (gt_id, str(item["evaluation_finding_id"])) in score_by_pair
                ]
                if len(options) < 2:
                    continue
                top_score = max(score for score, _signals in options)
                top_fingerprints = {_candidate_fingerprint(sig) for score, sig in options if abs(score - top_score) < 0.0001}
                if len(top_fingerprints) > 1:
                    tied_gt.add(gt_id)

        matches: list[dict[str, Any]] = []
        evaluation_time = evaluated_at or _STABLE_EVALUATION_TIME
        used_ai_ids = set(assigned.values())
        ai_by_id = {str(item["evaluation_finding_id"]): item for item in ai}

        for gt_item in sorted(ground_truth, key=lambda record: str(record["ground_truth_id"])):
            gt_id = str(gt_item["ground_truth_id"])
            ai_id = assigned.get(gt_id)
            if ai_id:
                item = ai_by_id[ai_id]
                signals = signals_by_pair[(gt_id, ai_id)]
                status = self._determine_status(signals, tied=gt_id in tied_gt)
                evidence_status, evidence_reason = _evidence_grounding(gt_item, item)
                severity_correct = signals["severity_match"]
                recommendation_correct = _equal_signal(gt_item.get("expected_recommendation"), item.get("recommendation"))
                rationale = (
                    f"contract_id and version_id matched; category_match={signals['category_match']}; "
                    f"clause_match={signals['clause_match']}; evidence_match={signals['evidence_match']}; "
                    f"finding_overlap={signals['finding_score']:.2f}; composite_score={signals['score']:.2f}; {evidence_reason}"
                )
                matches.append(self._match_record(org_id, evaluation_run_id, gt_item, item, status, signals, evidence_status, severity_correct, recommendation_correct, rationale, evaluation_time))
            else:
                matches.append(self._match_record(org_id, evaluation_run_id, gt_item, None, EvaluationMatchStatus.MISSED, {}, _UNKNOWN, None, None, "No candidate pair survived the 1.1.0 candidate gate for this ground-truth finding.", evaluation_time))

        for item in sorted(ai, key=lambda record: str(record["evaluation_finding_id"])):
            ai_id = str(item["evaluation_finding_id"])
            if ai_id in used_ai_ids:
                continue
            matches.append(self._match_record(org_id, evaluation_run_id, None, item, EvaluationMatchStatus.FALSE_POSITIVE, {}, _UNKNOWN, None, None, "AI finding was not selected by the 1.1.0 global assignment.", evaluation_time))

        metrics = self._metrics(org_id, evaluation_run_id, matches)
        return EvaluationResult(matches=matches, metrics=metrics)
