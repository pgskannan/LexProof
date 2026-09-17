"""Phase E.2 retrospective: Evaluator 1.0.0 vs 1.1.0 on the frozen baseline.

READ-ONLY. This script:
  - reads the 29 finalized ground-truth findings for the frozen internal
    benchmark dataset (9106833f-43df-4e0c-a78e-195ce30277af)
  - reads the 12 stored AI findings for the frozen baseline run
    (5f7e3387-74a3-4648-a474-9556ffddf9e7)
  - runs BOTH DeterministicEvaluationEngine (1.0.0) and
    DeterministicEvaluationEngineV1_1 (1.1.0) against those same records,
    entirely in memory
  - prints a full comparison report

It NEVER calls .set()/.delete() on any repository, never calls Gemini or any
other AI provider, never touches the blockchain, and never creates a new
evaluation_run record. The baseline run document itself is read once (to
confirm its identity/metadata) and never written to. Nothing here persists
anything -- rerun it as many times as you like.

Usage (from the backend/ directory, with your normal venv/credentials):
    python scripts/evaluator_1_1_0_retrospective.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings  # noqa: E402
from app.lexproof.repositories.firestore import FirestoreRepository  # noqa: E402
from app.lexproof.services.evaluation_engine import DeterministicEvaluationEngine  # noqa: E402
from app.lexproof.services.evaluation_engine_v1_1 import DeterministicEvaluationEngineV1_1  # noqa: E402

DATASET_ID = "9106833f-43df-4e0c-a78e-195ce30277af"
BASELINE_RUN_ID = "5f7e3387-74a3-4648-a474-9556ffddf9e7"

# From docs/AI_EVALUATION_BENCHMARK_V1.md -- the frozen dataset's own
# contract-id -> label mapping. Not re-derived from a live read of the
# `contracts` collection, specifically so this script never has to touch
# that (or any other) production collection.
CONTRACT_LABELS = {
    "645a2cd6-f436-4e6f-8b14-ac6240d6606a": "C2 (CONTRACT_02_MSA_MediumRisk.docx)",
    "50712c6d-cd84-408e-aac0-9c28ed09f2fe": "C6 (CONTRACT_06_DPA_ComplianceIssues.docx)",
    "897c9b37-b5a0-4853-b1c6-c42d2cdf1a18": "C8 (CONTRACT_08_JointVenture_ExecApproval.docx)",
}

EXPECTED_GT_COUNT = 29
EXPECTED_AI_COUNT = 12
EXPECTED_RUN_COUNT = 1
EXPECTED_MATCH_COUNT = 32
EXPECTED_METRICS_COUNT = 1
REFERENCE_GT_SHA = "94c271cea3f41bed907eb59db06b28343dd9bb81c4fa14e7c5af82c78252396c"


def _repos():
    settings = get_settings()
    return {
        "datasets": FirestoreRepository("evaluation_datasets", settings=settings),
        "runs": FirestoreRepository("evaluation_runs", settings=settings),
        "ground_truth": FirestoreRepository("evaluation_ground_truth_findings", settings=settings),
        "run_findings": FirestoreRepository("evaluation_run_findings", settings=settings),
        "matches": FirestoreRepository("evaluation_matches", settings=settings),
        "metrics": FirestoreRepository("evaluation_metrics", settings=settings),
    }


def _integrity_snapshot(repos: dict) -> dict:
    """Read-only counts, scoped to this dataset/run. Called before AND after
    the retrospective so the caller can prove this script wrote nothing."""
    return {
        "evaluation_runs": len(repos["runs"].query(equal={"dataset_version_id": DATASET_ID})),
        "evaluation_run_findings": len(repos["run_findings"].query(equal={"evaluation_run_id": BASELINE_RUN_ID})),
        "evaluation_matches": len(repos["matches"].query(equal={"evaluation_run_id": BASELINE_RUN_ID})),
        "evaluation_metrics": len(repos["metrics"].query(equal={"evaluation_run_id": BASELINE_RUN_ID})),
    }


def _gt_sha(ground_truth: list[dict]) -> str:
    """A canonical hash of the ground-truth content fields, sorted by
    ground_truth_id. NOTE: the exact canonicalization recipe that produced
    the frozen reference SHA in the Phase E.2 spec is not documented
    anywhere this script could read, so this hash is offered for
    comparison, not asserted as a match -- see the printed caveat."""
    fields = ("ground_truth_id", "contract_id", "version_id", "finding_category", "clause_reference", "expected_severity", "expected_finding", "expected_evidence", "expected_recommendation", "review_status")
    canonical = [
        {field: record.get(field) for field in fields}
        for record in sorted(ground_truth, key=lambda record: str(record["ground_truth_id"]))
    ]
    blob = json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _load(repos: dict) -> tuple[dict, dict, list[dict], list[dict]]:
    dataset = repos["datasets"].get(DATASET_ID)
    if not dataset:
        raise SystemExit(f"Dataset {DATASET_ID} not found -- has it moved or been renamed?")
    run = repos["runs"].get(BASELINE_RUN_ID)
    if not run:
        raise SystemExit(f"Baseline run {BASELINE_RUN_ID} not found -- has it moved or been renamed?")

    ground_truth = repos["ground_truth"].query(equal={"dataset_version_id": DATASET_ID})
    ai_findings = repos["run_findings"].query(equal={"evaluation_run_id": BASELINE_RUN_ID})
    return dataset, run, ground_truth, ai_findings


def _run_engine(engine_cls, org_id: str, run_id: str, dataset_id: str, ground_truth: list[dict], ai_findings: list[dict]):
    engine = engine_cls()
    return engine.evaluate(
        org_id=org_id,
        evaluation_run_id=run_id,
        dataset_version_id=dataset_id,
        ground_truth_findings=ground_truth,
        ai_findings=ai_findings,
        require_finalized=True,
    )


def _contract_metrics(engine, org_id: str, run_id: str, matches: list[dict], contract_id: str) -> dict:
    subset = [item for item in matches if item.get("contract_id") == contract_id]
    return engine._metrics(org_id, run_id, subset)  # reuses 1.0.0/1.1.0's own, unchanged metrics math


def _print_metrics(label: str, metrics: dict) -> None:
    def fmt(value):
        return "None" if value is None else (f"{value:.3f}" if isinstance(value, float) else value)

    print(f"\n-- {label} --")
    for key in (
        "true_positives", "false_positives", "false_negatives", "uncertain_count",
        "precision", "recall", "f1", "severity_accuracy", "critical_recall",
        "high_risk_recall", "evidence_grounding", "recommendation_accuracy",
    ):
        print(f"  {key}: {fmt(metrics.get(key))}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default=None, help="Optional path to also dump the full raw comparison as JSON.")
    args = parser.parse_args()

    repos = _repos()
    print("=" * 78)
    print("INTEGRITY SNAPSHOT -- BEFORE")
    print("=" * 78)
    before = _integrity_snapshot(repos)
    for key, expected in (("evaluation_runs", EXPECTED_RUN_COUNT), ("evaluation_run_findings", EXPECTED_AI_COUNT), ("evaluation_matches", EXPECTED_MATCH_COUNT), ("evaluation_metrics", EXPECTED_METRICS_COUNT)):
        flag = "" if before[key] == expected else "  <-- UNEXPECTED (expected %d)" % expected
        print(f"  {key}: {before[key]}{flag}")

    dataset, run, ground_truth, ai_findings = _load(repos)
    org_id = str(dataset["org_id"])

    print("\n" + "=" * 78)
    print("DATA INTEGRITY")
    print("=" * 78)
    print(f"Dataset: {DATASET_ID}  status={dataset.get('status')}  org_id={org_id}")
    print(f"Baseline run: {BASELINE_RUN_ID}  provider={run.get('provider')}  model={run.get('model')}")
    print(f"Ground-truth findings read: {len(ground_truth)} (expected {EXPECTED_GT_COUNT})")
    print(f"AI findings read: {len(ai_findings)} (expected {EXPECTED_AI_COUNT})")
    not_finalized = [g["ground_truth_id"] for g in ground_truth if g.get("review_status") != "FINALIZED"]
    if not_finalized:
        print(f"WARNING: {len(not_finalized)} ground-truth findings are not FINALIZED: {not_finalized}")
    if len(ground_truth) != EXPECTED_GT_COUNT or len(ai_findings) != EXPECTED_AI_COUNT:
        print("WARNING: record counts differ from the frozen baseline description -- the data may have drifted. Re-check before trusting the comparison below.")

    computed_sha = _gt_sha(ground_truth)
    print(f"\nGT SHA (this script's canonicalization): {computed_sha}")
    print(f"GT SHA (expected, from your spec):        {REFERENCE_GT_SHA}")
    if computed_sha == REFERENCE_GT_SHA:
        print("  MATCH.")
    else:
        print("  DIFFERS -- this does not necessarily mean the data changed: the exact field")
        print("  set/ordering/serialization used to produce the reference SHA isn't recorded")
        print("  anywhere this script could read, so this comparison can false-negative on a")
        print("  canonicalization mismatch even when the underlying 29 records are untouched.")
        print("  Treat the record counts and per-finding content above as the authoritative check.")

    legacy = _run_engine(DeterministicEvaluationEngine, org_id, BASELINE_RUN_ID, DATASET_ID, ground_truth, ai_findings)
    updated = _run_engine(DeterministicEvaluationEngineV1_1, org_id, BASELINE_RUN_ID, DATASET_ID, ground_truth, ai_findings)

    print("\n" + "=" * 78)
    print("EVALUATOR 1.0.0 vs 1.1.0 -- OVERALL METRICS  (retrospective analysis of baseline run, not a new run)")
    print("=" * 78)
    _print_metrics("1.0.0 (frozen, unchanged)", legacy.metrics)
    _print_metrics("1.1.0 (retrospective)", updated.metrics)

    for contract_id, label in CONTRACT_LABELS.items():
        print("\n" + "=" * 78)
        print(f"PER-CONTRACT: {label}")
        print("=" * 78)
        legacy_engine = DeterministicEvaluationEngine()
        updated_engine = DeterministicEvaluationEngineV1_1()
        _print_metrics("1.0.0", _contract_metrics(legacy_engine, org_id, BASELINE_RUN_ID, legacy.matches, contract_id))
        _print_metrics("1.1.0", _contract_metrics(updated_engine, org_id, BASELINE_RUN_ID, updated.matches, contract_id))

    print("\n" + "=" * 78)
    print("MATCH CHANGES (ground-truth findings whose status differs between versions)")
    print("=" * 78)
    legacy_by_gt = {item["ground_truth_id"]: item for item in legacy.matches if item.get("ground_truth_id")}
    updated_by_gt = {item["ground_truth_id"]: item for item in updated.matches if item.get("ground_truth_id")}
    changes = []
    for gt_id, new_item in updated_by_gt.items():
        old_item = legacy_by_gt.get(gt_id)
        if not old_item or old_item["status"] != new_item["status"]:
            changes.append((gt_id, old_item, new_item))
    if not changes:
        print("  (none)")
    for gt_id, old_item, new_item in changes:
        old_status = old_item["status"] if old_item else "N/A"
        print(f"\n  ground_truth_id={gt_id}")
        print(f"    old status: {old_status}   new status: {new_item['status']}")
        print(f"    new match_score={new_item.get('match_score')}  category_match={new_item.get('category_match')}  clause_match={new_item.get('clause_match')}  evidence_grounding={new_item.get('evidence_grounding')}")
        print(f"    rationale: {new_item.get('rationale')}")

    print("\n" + "=" * 78)
    print("REMAINING MISSED (1.1.0)")
    print("=" * 78)
    for item in updated.matches:
        if item["status"] == "MISSED":
            print(f"  ground_truth_id={item['ground_truth_id']}: {item.get('rationale')}")

    print("\n" + "=" * 78)
    print("REMAINING UNCERTAIN (1.1.0)")
    print("=" * 78)
    for item in updated.matches:
        if item["status"] == "UNCERTAIN":
            print(f"  ground_truth_id={item.get('ground_truth_id')} evaluation_finding_id={item.get('evaluation_finding_id')}: {item.get('rationale')}")

    print("\n" + "=" * 78)
    print("REMAINING FALSE POSITIVES (1.1.0)")
    print("=" * 78)
    for item in updated.matches:
        if item["status"] == "FALSE_POSITIVE":
            print(f"  evaluation_finding_id={item.get('evaluation_finding_id')}: {item.get('rationale')}")

    print("\n" + "=" * 78)
    print("SPECIAL-CASE VALIDATION")
    print("=" * 78)
    gt_by_id = {record["ground_truth_id"]: record for record in ground_truth}
    ai_by_id = {record["evaluation_finding_id"]: record for record in ai_findings}

    def _describe(gt_id, ai_id, label):
        print(f"\n  [{label}]")
        old = legacy_by_gt.get(gt_id) if gt_id else None
        new = updated_by_gt.get(gt_id) if gt_id else None
        if gt_id:
            print(f"    GT {gt_id}: category={gt_by_id.get(gt_id, {}).get('finding_category')!r} clause={gt_by_id.get(gt_id, {}).get('clause_reference')!r}")
        if ai_id:
            print(f"    AI {ai_id}: category={ai_by_id.get(ai_id, {}).get('finding_category')!r} clause={ai_by_id.get(ai_id, {}).get('clause_reference')!r}")
        print(f"    1.0.0: status={old.get('status') if old else 'N/A'} score={old.get('match_score') if old else 'N/A'}")
        print(f"    1.1.0: status={new.get('status') if new else 'N/A'} score={new.get('match_score') if new else 'N/A'} category_match={new.get('category_match') if new else 'N/A'} clause_match={new.get('clause_match') if new else 'N/A'} evidence_grounding={new.get('evidence_grounding') if new else 'N/A'}")

    # 1. C2 indemnification-style pair: found by category text, not id, since
    # ids aren't known ahead of time.
    indemnification_gt = [gid for gid, rec in gt_by_id.items() if "indemnif" in str(rec.get("finding_category", "")).lower()]
    indemnification_ai = [aid for aid, rec in ai_by_id.items() if "indemnif" in str(rec.get("finding_category", "")).lower()]
    if indemnification_gt:
        for gid in indemnification_gt:
            match = updated_by_gt.get(gid, {})
            _describe(gid, match.get("evaluation_finding_id"), "1. C2-style indemnification category correspondence")
    else:
        print("\n  [1. C2-style indemnification] No ground-truth finding with 'indemnif' in its category was found in the live data -- cannot validate this specific case; see the constructed unit test instead.")

    # 2. C6 Data Subject Rights pair.
    dsr_gt = [gid for gid, rec in gt_by_id.items() if "data subject" in str(rec.get("finding_category", "")).lower()]
    if dsr_gt:
        for gid in dsr_gt:
            match = updated_by_gt.get(gid, {})
            _describe(gid, match.get("evaluation_finding_id"), "2. C6-style Data Subject Rights correspondence")
    else:
        print("\n  [2. C6-style Data Subject Rights] No ground-truth finding with 'data subject' in its category was found in the live data -- cannot validate this specific case; see the constructed unit test instead.")

    # 3. Clause normalization spot-check across all loaded GT/AI clause text.
    from app.lexproof.services.evaluation_engine_v1_1 import normalize_clause
    print("\n  [3. Clause normalization spot-check across the live data]")
    all_clauses = {str(r.get("clause_reference")) for r in ground_truth if r.get("clause_reference")} | {str(r.get("clause_reference")) for r in ai_findings if r.get("clause_reference")}
    fee_clauses = [c for c in all_clauses if "3.1" in c or ("fee" in c.lower() and any(ch.isdigit() for ch in c))]
    for clause in sorted(fee_clauses):
        print(f"    {clause!r} -> normalized {normalize_clause(clause)!r}")
    if not fee_clauses:
        print("    No clause reference containing '3.1' was found in the live data -- see the direct unit test for the normalization proof instead.")

    # 4. Assignment collisions specifically in C6 / C8.
    print("\n  [4. Assignment collisions in C6 / C8]")
    for contract_id, label in CONTRACT_LABELS.items():
        if not label.startswith(("C6", "C8")):
            continue
        legacy_pairs = {item["ground_truth_id"]: item.get("evaluation_finding_id") for item in legacy.matches if item.get("contract_id") == contract_id and item.get("ground_truth_id")}
        updated_pairs = {item["ground_truth_id"]: item.get("evaluation_finding_id") for item in updated.matches if item.get("contract_id") == contract_id and item.get("ground_truth_id")}
        diffs = {gid: (legacy_pairs.get(gid), updated_pairs.get(gid)) for gid in set(legacy_pairs) | set(updated_pairs) if legacy_pairs.get(gid) != updated_pairs.get(gid)}
        if diffs:
            for gid, (old_ai, new_ai) in diffs.items():
                print(f"    {label}: GT {gid} was assigned to AI {old_ai!r} under 1.0.0, now assigned to AI {new_ai!r} under 1.1.0")
        else:
            print(f"    {label}: no assignment differences between 1.0.0 and 1.1.0")

    print("\n" + "=" * 78)
    print("BASELINE IMMUTABILITY")
    print("=" * 78)
    print(f"  Baseline run {BASELINE_RUN_ID} was only ever read (.get()), never written.")
    print("  No evaluation_matches or evaluation_metrics were persisted by this script for either engine version.")
    print("  No risk_findings / legal_passports / evidence_records / evidence_anchors / notifications / audit_events / contracts / contract_versions collection was read or written by this script.")

    print("\n" + "=" * 78)
    print("INTEGRITY SNAPSHOT -- AFTER")
    print("=" * 78)
    after = _integrity_snapshot(repos)
    all_unchanged = True
    for key in before:
        changed = before[key] != after[key]
        all_unchanged = all_unchanged and not changed
        flag = "  <-- CHANGED" if changed else "  (unchanged)"
        print(f"  {key}: before={before[key]} after={after[key]}{flag}")
    print(f"\n  Result: {'NO DRIFT -- this script wrote nothing.' if all_unchanged else 'DRIFT DETECTED -- something outside this script wrote to these collections during the run.'}")

    if args.json_path:
        payload = {
            "dataset_version_id": DATASET_ID,
            "baseline_run_id": BASELINE_RUN_ID,
            "ground_truth_count": len(ground_truth),
            "ai_finding_count": len(ai_findings),
            "legacy_metrics": legacy.metrics,
            "updated_metrics": updated.metrics,
            "legacy_matches": legacy.matches,
            "updated_matches": updated.matches,
        }
        Path(args.json_path).write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nFull raw comparison written to {args.json_path}")


if __name__ == "__main__":
    main()
