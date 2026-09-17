"""Phase E.3 design step: read-only text dump of the 18 remaining Evaluator 1.1.0
false negatives, plus all 12 stored AI findings, for textual/clause-based FN
classification.

READ-ONLY. Same access pattern as evaluator_1_1_0_retrospective.py:
  - reads the 29 finalized ground-truth findings for the frozen dataset
  - reads the 12 stored AI findings for the frozen baseline run
  - runs DeterministicEvaluationEngineV1_1 in memory to identify which 18 GT
    ids are currently MISSED (no candidate pair survived the gate)
  - prints full text (category, clause, severity, finding, evidence,
    recommendation) for those 18 GT records and for all 12 AI findings

It calls NO .set()/.delete() on any repository, calls no AI provider, touches
no blockchain, and creates no new evaluation_run record. Nothing here persists
anything -- rerun it as many times as you like.

Usage (from the backend/ directory, with your normal venv/credentials):
    python scripts/phase_e3_fn_dump.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings  # noqa: E402
from app.lexproof.repositories.firestore import FirestoreRepository  # noqa: E402
from app.lexproof.services.evaluation_engine_v1_1 import DeterministicEvaluationEngineV1_1  # noqa: E402

DATASET_ID = "9106833f-43df-4e0c-a78e-195ce30277af"
BASELINE_RUN_ID = "5f7e3387-74a3-4648-a474-9556ffddf9e7"

GT_FIELDS = (
    "ground_truth_id", "contract_id", "finding_category", "clause_reference",
    "expected_severity", "expected_finding", "expected_evidence",
    "expected_recommendation",
)
AI_FIELDS = (
    "evaluation_finding_id", "contract_id", "finding_category", "clause_reference",
    "severity", "finding", "evidence", "recommendation",
)


def _repos():
    settings = get_settings()
    return {
        "datasets": FirestoreRepository("evaluation_datasets", settings=settings),
        "runs": FirestoreRepository("evaluation_runs", settings=settings),
        "ground_truth": FirestoreRepository("evaluation_ground_truth_findings", settings=settings),
        "run_findings": FirestoreRepository("evaluation_run_findings", settings=settings),
    }


def _print_record(record: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in record:
            print(f"    {field}: {record.get(field)!r}")
    # Also print any other text-bearing keys this schema happens to use that
    # the field lists above didn't anticipate, so nothing is silently hidden.
    known = set(fields)
    for key, value in record.items():
        if key in known or key.endswith("_id") or key in ("created_at", "updated_at", "review_status", "org_id", "version_id"):
            continue
        if isinstance(value, str) and value.strip():
            print(f"    [other] {key}: {value!r}")


def main() -> None:
    repos = _repos()
    dataset = repos["datasets"].get(DATASET_ID)
    if not dataset:
        raise SystemExit(f"Dataset {DATASET_ID} not found.")
    run = repos["runs"].get(BASELINE_RUN_ID)
    if not run:
        raise SystemExit(f"Baseline run {BASELINE_RUN_ID} not found.")

    ground_truth = repos["ground_truth"].query(equal={"dataset_version_id": DATASET_ID})
    ai_findings = repos["run_findings"].query(equal={"evaluation_run_id": BASELINE_RUN_ID})
    org_id = str(dataset["org_id"])

    engine = DeterministicEvaluationEngineV1_1()
    result = engine.evaluate(
        org_id=org_id,
        evaluation_run_id=BASELINE_RUN_ID,
        dataset_version_id=DATASET_ID,
        ground_truth_findings=ground_truth,
        ai_findings=ai_findings,
        require_finalized=True,
    )
    missed_ids = {item["ground_truth_id"] for item in result.matches if item["status"] == "MISSED"}
    gt_by_id = {g["ground_truth_id"]: g for g in ground_truth}

    print("=" * 78)
    print(f"REMAINING FN (MISSED) UNDER EVALUATOR 1.1.0 -- full text ({len(missed_ids)} records)")
    print("=" * 78)
    for gt_id in sorted(missed_ids):
        record = gt_by_id.get(gt_id, {})
        print(f"\n  GT {gt_id}  (contract_id={record.get('contract_id')})")
        _print_record(record, GT_FIELDS)

    print("\n" + "=" * 78)
    print(f"ALL AI FINDINGS -- full text ({len(ai_findings)} records)")
    print("=" * 78)
    for record in sorted(ai_findings, key=lambda r: str(r.get("evaluation_finding_id"))):
        print(f"\n  AI {record.get('evaluation_finding_id')}  (contract_id={record.get('contract_id')})")
        _print_record(record, AI_FIELDS)


if __name__ == "__main__":
    main()
