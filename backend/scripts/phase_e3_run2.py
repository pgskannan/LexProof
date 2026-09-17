"""Phase E.3 / Experiment E3-A -- Run #2.

Executes exactly ONE Vertex AI Gemini benchmark run using the new analysis-1.1
prompt (see app/lexproof/services/analysis_prompt.py's
build_analysis_prompt_v1_1 -- a pure addition; analysis-1.0 is byte-for-byte
unchanged) against the three frozen benchmark members of dataset
9106833f-43df-4e0c-a78e-195ce30277af, then evaluates the result with the
frozen Evaluator 1.1.0 (evaluation_engine_v1_1.py -- also unchanged by this
script).

This does NOT call VersionAnalysisService, does NOT read or write
contracts.current_version_id, does NOT create legal_passports / evidence /
blockchain anchors / notifications / production risk_findings, and does NOT
touch baseline Run #1 (5f7e3387-74a3-4648-a474-9556ffddf9e7) -- that run is
only ever read once (a .get(), for a before/after identity check), never
written. It creates exactly one NEW evaluation_run (a fresh id; the run-key
is derived from prompt_version="analysis-1.1" + evaluator_version="1.1.0",
which necessarily differs from Run #1's key, so this cannot collide with or
reuse the baseline run) plus that run's own run_findings / matches / metrics.

The swap from analysis-1.0 to analysis-1.1 is done by temporarily reassigning
the `build_analysis_prompt` name inside the already-imported benchmark_runner
module object, for the lifetime of this process only, then restoring it in a
`finally` block. No file on disk is modified by this script.

Usage (from the backend/ directory, with your normal venv/credentials):
    python scripts/phase_e3_run2.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings  # noqa: E402
from app.lexproof.repositories.firestore import FirestoreRepository  # noqa: E402
from app.lexproof.services.analysis_prompt import (  # noqa: E402
    ANALYSIS_PROMPT_VERSION_1_1,
    build_analysis_prompt_v1_1,
)
from app.lexproof.services import benchmark_runner as benchmark_runner_module  # noqa: E402
from app.lexproof.services.benchmark_runner import BenchmarkRunService  # noqa: E402
from app.lexproof.services.evaluation import EvaluationService  # noqa: E402
from app.lexproof.services.evaluation_engine_v1_1 import DeterministicEvaluationEngineV1_1  # noqa: E402
from app.lexproof.services.organizations import OrganizationService  # noqa: E402

DATASET_ID = "9106833f-43df-4e0c-a78e-195ce30277af"
BASELINE_RUN_ID = "5f7e3387-74a3-4648-a474-9556ffddf9e7"
ORG_ID = "lexproof-demo"
AUTHENTICATED_USER_ID = "VJEexqdPVwYJ73D6vShQ75DSGdZ2"  # existing active member of lexproof-demo (scripts/create_approval_demo_fixture.py uses the same identity)

PRODUCTION_COLLECTIONS = [
    "risk_findings", "legal_passports", "evidence_records", "evidence_anchors",
    "notifications", "audit_events", "contracts", "contract_versions",
]


def _member() -> dict:
    """Build the same {uid, org_id, roles, email} shape services/auth.py's
    load_org_member() builds for a real authenticated HTTP request -- this
    script has no FastAPI request to go through, so it assembles it directly
    from the existing, already-active org membership record rather than
    fabricating a new one."""
    orgs = OrganizationService()
    record = orgs.get_active_member(ORG_ID, AUTHENTICATED_USER_ID)
    if not record:
        raise SystemExit(f"No active membership found for {AUTHENTICATED_USER_ID} in org {ORG_ID} -- aborting before making any changes.")
    return {
        "uid": AUTHENTICATED_USER_ID,
        "org_id": ORG_ID,
        "roles": list(record.get("roles") or []),
        "email": record.get("email"),
    }


def _evaluation_snapshot(evaluation: EvaluationService) -> dict:
    return {
        "evaluation_runs_for_dataset": len(evaluation.runs.query(equal={"dataset_version_id": DATASET_ID})),
        "evaluation_run_findings_all": len(evaluation.run_findings.query()),
        "evaluation_matches_all": len(evaluation.matches.query()),
        "evaluation_metrics_all": len(evaluation.metrics.query()),
    }


def _production_snapshot(settings) -> dict:
    return {name: len(FirestoreRepository(name, settings=settings).query()) for name in PRODUCTION_COLLECTIONS}


def _content_hashes(evaluation: EvaluationService) -> dict:
    rows = sorted(
        evaluation.members.query(equal={"dataset_version_id": DATASET_ID}),
        key=lambda row: str(row.get("added_at") or ""),
    )
    hashes: dict[str, str | None] = {}
    for row in rows:
        version = evaluation.versions.get(str(row.get("version_id") or "")) or {}
        hashes[str(row.get("contract_id"))] = version.get("content_hash")
    return hashes


async def main() -> None:
    settings = get_settings()
    evaluation = EvaluationService()
    member = _member()

    print(f"Resolved member: uid={member['uid']} org_id={member['org_id']} roles={member['roles']}")
    if not {"admin", "reviewer"} & {str(r).lower() for r in member["roles"]}:
        raise SystemExit(
            f"Resolved member has roles={member['roles']}, which does not include admin or reviewer -- "
            "create_run/get_dataset would reject this before any Gemini call is made. Aborting."
        )

    baseline_before = evaluation.runs.get(BASELINE_RUN_ID)
    if not baseline_before:
        raise SystemExit(f"Baseline run {BASELINE_RUN_ID} not found -- aborting before making any changes.")

    print("=" * 78)
    print("BEFORE SNAPSHOT")
    print("=" * 78)
    before_eval = _evaluation_snapshot(evaluation)
    before_prod = _production_snapshot(settings)
    before_hashes = _content_hashes(evaluation)
    for key, value in before_eval.items():
        print(f"  {key}: {value}")
    for key, value in before_prod.items():
        print(f"  production/{key}: {value}")
    for key, value in before_hashes.items():
        print(f"  content_hash[{key}]: {value}")

    original_builder = benchmark_runner_module.build_analysis_prompt
    benchmark_runner_module.build_analysis_prompt = build_analysis_prompt_v1_1
    try:
        runner = BenchmarkRunService(evaluation=evaluation, evaluator=DeterministicEvaluationEngineV1_1())
        print("\n" + "=" * 78)
        print(f"RUNNING EXPERIMENT E3-A -- prompt_version={ANALYSIS_PROMPT_VERSION_1_1}  evaluator_version=1.1.0  model={settings.gemini_model}  temperature={settings.gemini_temperature}  max_output_tokens={settings.gemini_max_output_tokens}")
        print("=" * 78)
        result = await runner.start_run(
            member,
            dataset_version_id=DATASET_ID,
            prompt_version=ANALYSIS_PROMPT_VERSION_1_1,
            evaluate_after=True,
        )
    finally:
        benchmark_runner_module.build_analysis_prompt = original_builder

    run = result["run"]
    run_id = run.get("evaluation_run_id")
    print(f"\n  reused_existing_run: {result['reused']}  (must be False -- a new run was expected)")
    print(f"  evaluation_run_id: {run_id}")
    print(f"  same_as_baseline_run_id: {run_id == BASELINE_RUN_ID}  (must be False)")
    print(f"  status: {run.get('status')}")
    print(f"  provider: {run.get('provider')}  model: {run.get('model')}  model_version: {run.get('model_version')}")
    print(f"  prompt_version: {run.get('prompt_version')}  evaluator_version: {run.get('evaluator_version')}")
    print(f"  failed_contract_ids: {run.get('failed_contract_ids')}")
    print(f"  contract_errors: {run.get('contract_errors')}")
    print(f"  contract_warnings: {run.get('contract_warnings')}")
    print(f"  ai_finding_count: {run.get('ai_finding_count')}")
    print(f"  error_summary: {run.get('error_summary')}")
    print(f"\n  metrics: {result.get('metrics')}")

    print("\n" + "=" * 78)
    print("AFTER SNAPSHOT")
    print("=" * 78)
    after_eval = _evaluation_snapshot(evaluation)
    after_prod = _production_snapshot(settings)
    after_hashes = _content_hashes(evaluation)
    for key in before_eval:
        print(f"  {key}: before={before_eval[key]} after={after_eval[key]}")
    for key in before_prod:
        changed = "  <-- CHANGED" if before_prod[key] != after_prod[key] else "  (unchanged)"
        print(f"  production/{key}: before={before_prod[key]} after={after_prod[key]}{changed}")
    for key in before_hashes:
        changed = "  <-- CHANGED" if before_hashes[key] != after_hashes.get(key) else "  (unchanged)"
        print(f"  content_hash[{key}]: before={before_hashes[key]} after={after_hashes.get(key)}{changed}")

    baseline_after = evaluation.runs.get(BASELINE_RUN_ID)
    print(f"\n  Baseline run {BASELINE_RUN_ID} bit-identical after this script: {baseline_after == baseline_before}")

    print("\n" + "=" * 78)
    print("RUN #2 -- NEW AI FINDINGS BY CONTRACT")
    print("=" * 78)
    new_findings = evaluation.list_run_findings(member, run_id)
    by_contract: dict[str, list[dict]] = {}
    for finding in new_findings:
        by_contract.setdefault(str(finding.get("contract_id")), []).append(finding)
    for contract_id, items in sorted(by_contract.items()):
        print(f"\n  contract_id={contract_id}  count={len(items)}")
        for finding in items:
            print(f"    id={finding.get('evaluation_finding_id')}")
            print(f"      [{finding.get('severity')}] {finding.get('finding_category')} ({finding.get('clause_reference')})")
            print(f"      finding: {finding.get('finding')}")
            print(f"      evidence: {finding.get('evidence')}")

    print("\n" + "=" * 78)
    print("RUN #2 -- MATCH DETAIL (Evaluator 1.1.0)")
    print("=" * 78)
    matches = evaluation.matches.query(equal={"evaluation_run_id": run_id})
    for item in sorted(matches, key=lambda m: str(m.get("status"))):
        print(f"  status={item.get('status'):<15} ground_truth_id={item.get('ground_truth_id')}  evaluation_finding_id={item.get('evaluation_finding_id')}  score={item.get('match_score')}")
        print(f"    rationale: {item.get('rationale')}")


if __name__ == "__main__":
    asyncio.run(main())
