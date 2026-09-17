"""Phase E.3-B diagnostic -- READ-ONLY, NOT part of the production code path.

Forensic audit of why recommendation_accuracy = 0.000 in both Run #1
(5f7e3387-...) and Run #2 (2dd66e55-...). This script:

  - reads the 29 finalized ground-truth findings (dataset 9106833f-...)
  - reads the stored evaluation_run_findings for both runs
  - reads the already-persisted evaluation_matches and evaluation_metrics for
    both runs (it does NOT recompute or re-run the evaluator)
  - imports and calls the REAL, unmodified recommendation comparator
    (_equal_signal) and the REAL normalize_text/text_tokens/overlap_score
    helpers directly from evaluation_engine.py -- nothing here reimplements
    or approximates that logic, so the "real comparator, recomputed" column
    is the actual production function, not a stand-in for it
  - additionally computes a diagnostic-only token-overlap ratio using the
    same overlap_score() helper the evaluator uses for OTHER signals, purely
    to answer "are these recommendations lexically related at all" -- this
    diagnostic number is never fed back into any evaluator, match, or metric

It calls no LLM, creates no evaluation run, and writes nothing to any
collection -- read-only Firestore .get()/.query() calls only.

Usage (from backend/, with your normal venv/credentials):
    python scripts/phase_e3b_recommendation_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings  # noqa: E402
from app.lexproof.repositories.firestore import FirestoreRepository  # noqa: E402
from app.lexproof.services.evaluation_engine import (  # noqa: E402
    _equal_signal,
    normalize_text,
    overlap_score,
    text_tokens,
)

DATASET_ID = "9106833f-43df-4e0c-a78e-195ce30277af"
RUN_1 = "5f7e3387-74a3-4648-a474-9556ffddf9e7"
RUN_2 = "2dd66e55-1a6e-490f-a70f-718c8bf844af"

CONTRACT_LABELS = {
    "645a2cd6-f436-4e6f-8b14-ac6240d6606a": "C2",
    "50712c6d-cd84-408e-aac0-9c28ed09f2fe": "C6",
    "897c9b37-b5a0-4853-b1c6-c42d2cdf1a18": "C8",
}


def _repos():
    settings = get_settings()
    return {
        "ground_truth": FirestoreRepository("evaluation_ground_truth_findings", settings=settings),
        "run_findings": FirestoreRepository("evaluation_run_findings", settings=settings),
        "matches": FirestoreRepository("evaluation_matches", settings=settings),
        "metrics": FirestoreRepository("evaluation_metrics", settings=settings),
    }


def _classify_recommendation(text: str | None) -> str:
    """Diagnostic-only heuristic bucket for Step 8 -- not used by any evaluator."""
    if not text or not str(text).strip():
        return "empty/null"
    normalized = normalize_text(text)
    if len(normalized.split()) <= 4:
        return "generic (very short)"
    return "actionable/clause-specific (length-based heuristic only)"


def main() -> None:
    repos = _repos()
    ground_truth = {
        record["ground_truth_id"]: record
        for record in repos["ground_truth"].query(equal={"dataset_version_id": DATASET_ID})
    }

    print("=" * 78)
    print(f"STEP 8 -- GT expected_recommendation, all {len(ground_truth)} FINALIZED findings")
    print("=" * 78)
    buckets: dict[str, int] = {}
    for gt_id in sorted(ground_truth):
        record = ground_truth[gt_id]
        rec = record.get("expected_recommendation")
        bucket = _classify_recommendation(rec)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        label = CONTRACT_LABELS.get(str(record.get("contract_id")), "?")
        print(f"  {gt_id}  [{label}]  bucket={bucket}")
        print(f"    {rec!r}")
    print("\n  Bucket counts:")
    for bucket, count in sorted(buckets.items()):
        print(f"    {bucket}: {count}")

    for run_id, label in ((RUN_1, "RUN #1 (analysis-1.0)"), (RUN_2, "RUN #2 (analysis-1.1)")):
        print("\n" + "=" * 78)
        print(f"{label}  evaluation_run_id={run_id}")
        print("=" * 78)
        ai_findings = {
            record["evaluation_finding_id"]: record
            for record in repos["run_findings"].query(equal={"evaluation_run_id": run_id})
        }
        matches = repos["matches"].query(equal={"evaluation_run_id": run_id})
        metrics = repos["metrics"].query(equal={"evaluation_run_id": run_id})
        stored_metric = metrics[0].get("recommendation_accuracy") if metrics else "N/A"
        print(f"  stored evaluation_metrics.recommendation_accuracy = {stored_metric}")

        matched = [item for item in matches if item.get("status") == "MATCHED"]
        print(f"  MATCHED pairs in this run: {len(matched)}")

        non_none_results = []
        for item in sorted(matched, key=lambda record: str(record.get("ground_truth_id"))):
            gt_id = item.get("ground_truth_id")
            ai_id = item.get("evaluation_finding_id")
            gt_record = ground_truth.get(gt_id, {})
            ai_record = ai_findings.get(ai_id, {})
            gt_rec = gt_record.get("expected_recommendation")
            ai_rec = ai_record.get("recommendation")

            # THE REAL, UNMODIFIED comparator -- imported directly from
            # evaluation_engine.py, not reimplemented here.
            real_result = _equal_signal(gt_rec, ai_rec)
            stored_result = item.get("recommendation_correct")

            gt_norm = normalize_text(gt_rec)
            ai_norm = normalize_text(ai_rec)
            diagnostic_overlap = overlap_score(gt_rec, ai_rec)  # diagnostic only
            gt_tok = text_tokens(gt_rec)
            ai_tok = text_tokens(ai_rec)
            shared = gt_tok & ai_tok

            if real_result is not None:
                non_none_results.append(real_result)

            print(f"\n  GT {gt_id}  AI {ai_id}")
            print(f"    GT recommendation: {gt_rec!r}")
            print(f"    AI recommendation: {ai_rec!r}")
            print(f"    normalize_text(GT): {gt_norm!r}")
            print(f"    normalize_text(AI): {ai_norm!r}")
            print(f"    exact-match after normalization: {gt_norm == ai_norm}")
            print(f"    _equal_signal (REAL comparator, recomputed now): {real_result}")
            print(f"    stored recommendation_correct on this match record: {stored_result}")
            print(f"    recomputed == stored: {real_result == stored_result}")
            print(f"    diagnostic token overlap (NOT used by evaluator for this field): {diagnostic_overlap:.3f}  shared_tokens={sorted(shared)}")

        true_count = sum(1 for value in non_none_results if value is True)
        print(f"\n  Recomputed over MATCHED pairs: {len(non_none_results)} non-None, {true_count} True -> ratio {(true_count / len(non_none_results)) if non_none_results else 'N/A (no non-None values -> None, not 0.0)'}")


if __name__ == "__main__":
    main()
