"""Phase E4 -- controlled mechanical setup for LexProof Expansion Benchmark v2.

READ THIS BEFORE RUNNING. This script performs the ONLY writes this phase
authorizes, each preceded by a read-only verification:

  1. Upload contract C1 (CONTRACT_01_NDA_Clean_LowRisk.docx) via the exact
     same persistence path production upload uses --
     app.lexproof.api.contracts._persist_upload() -- ONLY if a contract with
     that exact filename is not already present. No synthetic records, no
     bypassed extraction/hashing.
  2. Create exactly one evaluation dataset ("LexProof Expansion Benchmark
     v2", version_label "v2.0-draft", status DRAFT, review_type
     INTERNAL_REVIEW, ground_truth_source INTERNAL_HUMAN_REVIEW, ai_blind
     True) via EvaluationService.create_dataset() -- unless a dataset with
     that exact name already exists as a DRAFT (resume, never duplicate).
  3. Add exactly five dataset members (C1 + the canonical C3/C4/C5/C7
     contract/version pairs) via EvaluationService.add_dataset_member().

It does NOT: create or modify any ground-truth finding, touch Dataset v1
(9106833f-43df-4e0c-a78e-195ce30277af) or its C2/C6/C8 membership/GT, call
any AI/LLM provider, create any evaluation run, modify any evaluator
(1.0.0/1.1.0/1.2.0), modify the analysis prompt, modify any production
risk_findings/passport/evidence/anchor record, or invent any new API route
-- only the existing EvaluationService methods and the existing
contract-upload persistence function are used.

If ANY verification fails, or ANY unexpected state is detected (an existing
duplicate v2 dataset, an unresolvable canonical pair, a Dataset v1 change,
an unexpected member, a partial write failure), the script prints STOPPED
with the exact reason and performs NO further writes. It never retries a
failed write automatically.

Safe to re-run: every write step first checks whether its target already
exists (by filename, by dataset name, by dataset-membership) and skips
re-creating it, so a second run after a clean completion is a no-op
verification pass, and a second run after a STOP resumes from wherever the
first run left off rather than duplicating anything.

Usage (from backend/, with your normal venv/credentials):
    python scripts/phase_e4_dataset_v2_setup.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.api.contracts import _persist_upload  # noqa: E402
from app.lexproof.config import get_settings  # noqa: E402
from app.lexproof.repositories.cloud_storage import CloudStorageRepository  # noqa: E402
from app.lexproof.repositories.firestore import FirestoreRepository  # noqa: E402
from app.lexproof.services.evaluation import (  # noqa: E402
    EvaluationError,
    EvaluationPermissionError,
    EvaluationReviewType,
    EvaluationService,
    GroundTruthSource,
)
from app.lexproof.services.organizations import OrganizationService  # noqa: E402

ORG_ID = "lexproof-demo"
AUTHENTICATED_USER_ID = "VJEexqdPVwYJ73D6vShQ75DSGdZ2"

DATASET_V1_ID = "9106833f-43df-4e0c-a78e-195ce30277af"
EXPECTED_V1_GT_BY_CONTRACT = {
    "645a2cd6-f436-4e6f-8b14-ac6240d6606a": ("C2", 8),
    "50712c6d-cd84-408e-aac0-9c28ed09f2fe": ("C6", 11),
    "897c9b37-b5a0-4853-b1c6-c42d2cdf1a18": ("C8", 10),
}
EXPECTED_V1_MEMBER_COUNT = 3
EXPECTED_V1_GT_TOTAL = 29

C1_FILENAME = "CONTRACT_01_NDA_Clean_LowRisk.docx"
C1_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
C1_LOCAL_PATH = Path(__file__).resolve().parents[2] / "sampleContracts" / C1_FILENAME

CANONICAL_PAIRS = {
    "C3": {"contract_id": "fd4f9738-8222-406e-a982-7a887b7f3016", "version_id": "7b3e9c15-bcc2-4615-8529-0bb22054c200"},
    "C4": {"contract_id": "cd026489-d06a-4874-9d31-616b6f1791a3", "version_id": "281b78e1-c5fc-44cd-98d7-7d20d6683278"},
    "C5": {"contract_id": "9c7a4f61-4f4f-4aa3-8d20-04a8b0d3d29f", "version_id": "9e41d9e2-ed20-4eb9-8142-de06cc94949b"},
    "C7": {"contract_id": "f4612308-aaae-4ad4-b5ce-639e83c8e078", "version_id": "a0cc91a0-ff88-4b98-ab08-e51828a6db14"},
}

DATASET_V2_NAME = "LexProof Expansion Benchmark v2"
DATASET_V2_VERSION_LABEL = "v2.0-draft"
DATASET_V2_DESCRIPTION = (
    "Phase E4 expansion benchmark: C1, C3, C4, C5, C7. AI-blind, internal "
    "human review. Dataset v1 (9106833f-...) remains the frozen, separate "
    "29-finding benchmark and is never modified by this dataset's lifecycle."
)

PRODUCTION_COLLECTIONS = [
    "contracts", "contract_versions", "risk_findings", "legal_passports",
    "evidence_records", "evidence_anchors", "notifications", "audit_events",
]
EVALUATION_COLLECTIONS = [
    "evaluation_datasets", "evaluation_dataset_members",
    "evaluation_ground_truth_findings", "evaluation_runs",
    "evaluation_run_findings", "evaluation_matches", "evaluation_metrics",
]


class Stop(Exception):
    """Raised anywhere below to abort with a precise, reportable reason."""


def _member() -> dict:
    orgs = OrganizationService()
    record = orgs.get_active_member(ORG_ID, AUTHENTICATED_USER_ID)
    if not record:
        raise Stop(f"No active membership found for {AUTHENTICATED_USER_ID} in org {ORG_ID} -- aborting before making any changes.")
    return {"uid": AUTHENTICATED_USER_ID, "org_id": ORG_ID, "roles": list(record.get("roles") or []), "email": record.get("email")}


def _snapshot(evaluation: EvaluationService, contracts: FirestoreRepository, versions: FirestoreRepository) -> dict:
    """Full before/after snapshot across every collection this phase reports on."""
    all_datasets = list(evaluation.datasets.stream())
    all_members = list(evaluation.members.stream())
    all_gt = list(evaluation.ground_truth.stream())
    v1 = evaluation.datasets.get(DATASET_V1_ID) or {}
    v1_members = [m for m in all_members if m.get("dataset_version_id") == DATASET_V1_ID]
    v1_gt = [g for g in all_gt if g.get("dataset_version_id") == DATASET_V1_ID]
    counts = {
        "contracts": len(list(contracts.stream())),
        "contract_versions": len(list(versions.stream())),
        "risk_findings": len(list(FirestoreRepository("risk_findings").stream())),
        "legal_passports": len(list(FirestoreRepository("legal_passports").stream())),
        "evidence_records": len(list(FirestoreRepository("evidence_records").stream())),
        "evidence_anchors": len(list(FirestoreRepository("evidence_anchors").stream())),
        "notifications": len(list(FirestoreRepository("notifications").stream())),
        "audit_events": len(list(FirestoreRepository("audit_events").stream())),
        "evaluation_datasets": len(all_datasets),
        "evaluation_dataset_members": len(all_members),
        "evaluation_ground_truth_findings": len(all_gt),
        "evaluation_runs": len(list(evaluation.runs.stream())),
        "evaluation_run_findings": len(list(evaluation.run_findings.stream())),
        "evaluation_matches": len(list(evaluation.matches.stream())),
        "evaluation_metrics": len(list(evaluation.metrics.stream())),
    }
    return {
        "counts": counts,
        "dataset_v1_status": v1.get("status"),
        "dataset_v1_member_count": len(v1_members),
        "dataset_v1_gt_count": len(v1_gt),
        "dataset_v1_gt_by_contract": dict(Counter(str(g.get("contract_id")) for g in v1_gt)),
        "all_datasets": all_datasets,
    }


def _section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def _print_snapshot_table(before: dict, after: dict) -> None:
    rows = list(PRODUCTION_COLLECTIONS) + list(EVALUATION_COLLECTIONS)
    print(f"  {'Resource':<32} {'Before':>8} {'After':>8} {'Delta':>7}")
    for key in rows:
        b, a = before["counts"][key], after["counts"][key]
        print(f"  {key:<32} {b:>8} {a:>8} {a - b:>+7}")
    print(f"\n  {'Dataset v1 status':<32} {before['dataset_v1_status']!s:>8} {after['dataset_v1_status']!s:>8}  {'OK' if before['dataset_v1_status'] == after['dataset_v1_status'] else '<<< CHANGED'}")
    print(f"  {'Dataset v1 member_count':<32} {before['dataset_v1_member_count']:>8} {after['dataset_v1_member_count']:>8}  {'OK' if before['dataset_v1_member_count'] == after['dataset_v1_member_count'] else '<<< CHANGED'}")
    print(f"  {'Dataset v1 gt_count':<32} {before['dataset_v1_gt_count']:>8} {after['dataset_v1_gt_count']:>8}  {'OK' if before['dataset_v1_gt_count'] == after['dataset_v1_gt_count'] else '<<< CHANGED'}")


def main() -> None:
    settings = get_settings()
    contracts = FirestoreRepository("contracts", settings=settings)
    versions = FirestoreRepository("contract_versions", settings=settings)
    storage = CloudStorageRepository(settings=settings)
    evaluation = EvaluationService()

    dataset_version_id = None
    c1_pair = None
    c1_status = "NOT ATTEMPTED"
    dataset_status = "NOT ATTEMPTED"
    member_rows = []

    before = None
    try:
        member = _member()
        before = _snapshot(evaluation, contracts, versions)

        # ---------------- STEP 1: PREFLIGHT (read-only) ----------------
        _section("STEP 1 -- PREFLIGHT (read-only)")
        print(f"  Dataset v1 status: {before['dataset_v1_status']}  (expected FINALIZED)")
        print(f"  Dataset v1 member_count: {before['dataset_v1_member_count']}  (expected {EXPECTED_V1_MEMBER_COUNT})")
        print(f"  Dataset v1 GT total: {before['dataset_v1_gt_count']}  (expected {EXPECTED_V1_GT_TOTAL})")
        if before["dataset_v1_status"] != "FINALIZED" or before["dataset_v1_member_count"] != EXPECTED_V1_MEMBER_COUNT or before["dataset_v1_gt_count"] != EXPECTED_V1_GT_TOTAL:
            raise Stop(f"Dataset v1 preflight mismatch. status={before['dataset_v1_status']!r} member_count={before['dataset_v1_member_count']} gt_count={before['dataset_v1_gt_count']}")
        for cid, (label, expected) in EXPECTED_V1_GT_BY_CONTRACT.items():
            actual = before["dataset_v1_gt_by_contract"].get(cid, 0)
            print(f"    {label} ({cid}): expected={expected} actual={actual}  {'OK' if actual == expected else '<<< STOP -- PRESERVATION MISMATCH'}")
            if actual != expected:
                raise Stop(f"STOP -- PRESERVATION MISMATCH: {label} expected {expected} GT, found {actual}.")

        print("\n  Canonical C3/C4/C5/C7 resolution:")
        for label, pair in CANONICAL_PAIRS.items():
            contract = contracts.get(pair["contract_id"])
            version = versions.get(pair["version_id"])
            belongs = bool(version) and version.get("contract_id") == pair["contract_id"]
            has_hash = bool(version) and bool(version.get("content_hash"))
            text_chars = len((version.get("document_text") or "")) if version else 0
            ok = bool(contract) and bool(version) and belongs and has_hash and text_chars > 0
            print(f"    {label}: contract={'found' if contract else 'MISSING'}  version={'found' if version else 'MISSING'}  "
                  f"belongs_to_contract={belongs}  content_hash={'present' if has_hash else 'MISSING'}  "
                  f"text_chars={text_chars}  -> {'OK' if ok else '<<< STOP'}")
            if not ok:
                raise Stop(f"Canonical pair for {label} does not resolve cleanly (contract_id={pair['contract_id']}, version_id={pair['version_id']}).")

        existing_c1 = next((c for c in contracts.stream() if c.get("name") == C1_FILENAME), None)
        if existing_c1:
            c1_contract_id = str(existing_c1.get("id"))
            c1_version_id = str(existing_c1.get("current_version_id"))
            v = versions.get(c1_version_id)
            ok = bool(v) and v.get("contract_id") == c1_contract_id and bool(v.get("content_hash")) and bool((v.get("document_text") or "").strip())
            print(f"\n  C1 ({C1_FILENAME}) ALREADY PRESENT: contract_id={c1_contract_id} version_id={c1_version_id} -> {'OK, will reuse (no re-upload)' if ok else '<<< STOP -- malformed existing record'}")
            if not ok:
                raise Stop(f"C1 already present as contract_id={c1_contract_id} but its version record is malformed -- refusing to reuse or duplicate.")
            c1_pair = {"contract_id": c1_contract_id, "version_id": c1_version_id}
            c1_status = "ALREADY_PRESENT_VERIFIED_REUSED"
        else:
            print(f"\n  C1 ({C1_FILENAME}) is absent from Firestore -- will upload via the normal contract-upload persistence path.")
            if not C1_LOCAL_PATH.exists():
                raise Stop(f"C1 local source file not found at {C1_LOCAL_PATH} -- cannot upload.")

        existing_v2 = [d for d in before["all_datasets"] if d.get("name") == DATASET_V2_NAME]
        if len(existing_v2) > 1:
            raise Stop(f"Found {len(existing_v2)} existing datasets named {DATASET_V2_NAME!r} -- unexpected duplicate, refusing to proceed automatically.")
        resumed_dataset = existing_v2[0] if existing_v2 else None
        if resumed_dataset:
            if resumed_dataset.get("status") == "FINALIZED":
                raise Stop(f"Dataset {DATASET_V2_NAME!r} already exists and is FINALIZED ({resumed_dataset.get('dataset_version_id')}) -- this script only ever creates a DRAFT dataset, refusing to touch a finalized one.")
            dataset_version_id = str(resumed_dataset.get("dataset_version_id"))
            print(f"\n  Dataset {DATASET_V2_NAME!r} already exists as a DRAFT ({dataset_version_id}) -- will resume/verify membership rather than create a new one.")
        else:
            print(f"\n  No existing dataset named {DATASET_V2_NAME!r} -- will create it in STEP 3.")

        # ---------------- STEP 2: UPLOAD C1 (only if absent) ----------------
        _section("STEP 2 -- UPLOAD C1")
        if c1_pair is not None:
            print(f"  C1 upload not needed -- reusing existing verified pair {c1_pair}")
        else:
            content = C1_LOCAL_PATH.read_bytes()
            result = _persist_upload(
                C1_FILENAME, content, C1_CONTENT_TYPE, AUTHENTICATED_USER_ID, ORG_ID,
                contracts, versions, storage, actor_email=member.get("email"),
            )
            c1_pair = {"contract_id": result["contract_id"], "version_id": result["version_id"]}
            v = versions.get(c1_pair["version_id"])
            text_chars = len((v.get("document_text") or "")) if v else 0
            ok = bool(v) and bool(v.get("content_hash")) and text_chars > 0
            print(f"  Uploaded: contract_id={c1_pair['contract_id']}  version_id={c1_pair['version_id']}  content_hash={result['content_hash']}")
            print(f"  Extracted text_chars={text_chars}  ocr_status={result.get('ocr_status')}  -> {'OK' if ok else '<<< STOP -- post-upload verification failed'}")
            if not ok:
                raise Stop("C1 upload completed but post-upload verification found an empty or malformed version record. Reporting partial state -- do not retry blindly.")
            c1_status = "UPLOADED_AND_VERIFIED"

        expected_members = {"C1": c1_pair, **CANONICAL_PAIRS}

        # ---------------- STEP 3: CREATE DATASET V2 ----------------
        _section("STEP 3 -- CREATE DATASET V2")
        if dataset_version_id is not None:
            print(f"  Reusing existing DRAFT dataset {dataset_version_id}")
            dataset_status = "REUSED_EXISTING_DRAFT"
        else:
            record = evaluation.create_dataset(
                member,
                name=DATASET_V2_NAME,
                description=DATASET_V2_DESCRIPTION,
                version_label=DATASET_V2_VERSION_LABEL,
                review_type=EvaluationReviewType.INTERNAL_REVIEW,
                reviewer_type="INTERNAL_REVIEWER",
                reviewer_id=None,
                ai_blind=True,
                ground_truth_source=GroundTruthSource.INTERNAL_HUMAN_REVIEW,
            )
            dataset_version_id = record["dataset_version_id"]
            print(f"  Created dataset_version_id={dataset_version_id}")
            print(f"  name={record['name']!r}  version_label={record['version_label']!r}  status={record['status']}")
            print(f"  review_type={record['review_type']}  ground_truth_source={record['ground_truth_source']}  ai_blind={record['ai_blind']}")
            dataset_status = "CREATED"

        # ---------------- STEP 4: ADD 5 MEMBERS ----------------
        _section("STEP 4 -- ADD DATASET MEMBERS")
        current_member_pairs = {
            (m.get("contract_id"), m.get("version_id"))
            for m in evaluation.members.stream()
            if m.get("dataset_version_id") == dataset_version_id
        }
        for label, pair in expected_members.items():
            already = (pair["contract_id"], pair["version_id"]) in current_member_pairs
            content = contracts.get(pair["contract_id"])
            vers = versions.get(pair["version_id"])
            content_hash = vers.get("content_hash") if vers else None
            if already:
                print(f"  {label}: contract_id={pair['contract_id']} version_id={pair['version_id']}  already a member -- skipped (idempotent resume)")
                member_rows.append((label, pair["contract_id"], pair["version_id"], bool(content), content_hash, "already_present", label != "C1"))
                continue
            if not content or not vers:
                raise Stop(f"{label}: contract/version no longer resolves at add-time (contract_id={pair['contract_id']}, version_id={pair['version_id']}) -- refusing to add.")
            evaluation.add_dataset_member(member, dataset_version_id=dataset_version_id, contract_id=pair["contract_id"], version_id=pair["version_id"])
            print(f"  {label}: added contract_id={pair['contract_id']} version_id={pair['version_id']} content_hash={content_hash}")
            member_rows.append((label, pair["contract_id"], pair["version_id"], True, content_hash, "added", label != "C1"))

        # ---------------- STEP 5: VERIFY DATASET V2 ----------------
        _section("STEP 5 -- VERIFY DATASET V2")
        final_dataset = evaluation.datasets.get(dataset_version_id) or {}
        actual_members = [m for m in evaluation.members.stream() if m.get("dataset_version_id") == dataset_version_id]
        actual_gt = [g for g in evaluation.ground_truth.stream() if g.get("dataset_version_id") == dataset_version_id]
        actual_pairs = {(m.get("contract_id"), m.get("version_id")) for m in actual_members}
        expected_pairs = {(p["contract_id"], p["version_id"]) for p in expected_members.values()}
        unexpected = actual_pairs - expected_pairs
        missing = expected_pairs - actual_pairs
        print(f"  stored contract_count={final_dataset.get('contract_count')}  actual_member_count={len(actual_members)}  (expected 5)")
        print(f"  GT count for this dataset: {len(actual_gt)}  (expected 0)")
        print(f"  unexpected members: {unexpected or 'none'}")
        print(f"  missing expected members: {missing or 'none'}")
        v2_ok = len(actual_members) == 5 and len(actual_gt) == 0 and not unexpected and not missing
        if not v2_ok:
            raise Stop(f"Dataset v2 verification failed: member_count={len(actual_members)} gt_count={len(actual_gt)} unexpected={unexpected} missing={missing}")

        after = _snapshot(evaluation, contracts, versions)
        v1_unchanged = (
            after["dataset_v1_status"] == before["dataset_v1_status"]
            and after["dataset_v1_member_count"] == before["dataset_v1_member_count"]
            and after["dataset_v1_gt_count"] == before["dataset_v1_gt_count"]
        )
        print(f"  Dataset v1 unchanged: {v1_unchanged}")
        if not v1_unchanged:
            raise Stop("Dataset v1 changed during this run -- STOP IMMEDIATELY per instruction.")

        # ---------------- STEP 6: REVIEWER UI/API DISCOVERY ----------------
        _section("STEP 6 -- REVIEWER UI/API VERIFICATION")
        discoverable = [
            d for d in evaluation.datasets.stream()
            if d.get("org_id") == ORG_ID and d.get("review_type") == "INTERNAL_REVIEW"
        ]
        names = sorted(d.get("name") for d in discoverable)
        v1_visible = any(d.get("dataset_version_id") == DATASET_V1_ID for d in discoverable)
        v2_visible = any(d.get("dataset_version_id") == dataset_version_id for d in discoverable)
        print("  Replicated the exact GET /benchmarks filter (org_id + review_type==INTERNAL_REVIEW) in-process:")
        print(f"    datasets returned: {names}")
        print(f"    Dataset v1 discoverable: {v1_visible}")
        print(f"    Dataset v2 discoverable: {v2_visible}")
        print(f"    Dataset v2 ai_blind: {final_dataset.get('ai_blind')}")
        print(f"    Dataset v2 GT displayed to reviewer: {len(actual_gt)} (must be 0 pre-authoring)")
        print("  (This script does not drive a live browser session; the reviewer UI at "
              "frontend/.../benchmarks/page.tsx populates its dropdown from exactly this same "
              "GET /benchmarks query with no dataset-specific code, so this in-process replication "
              "is authoritative for what that route and that page will return.)")

        # ---------------- STEP 7: INTEGRITY SNAPSHOT ----------------
        _section("STEP 7 -- INTEGRITY SNAPSHOT (before/after)")
        _print_snapshot_table(before, after)

        # ---------------- STEP 8: LLM/AI VERIFICATION ----------------
        _section("STEP 8 -- LLM/AI VERIFICATION")
        print("  Gemini calls made by this script: 0 (no such import exists in this script)")
        print("  Vertex calls made by this script: 0 (no such import exists in this script)")
        print("  Other LLM calls made by this script: 0")
        print(f"  evaluation_runs before={before['counts']['evaluation_runs']} after={after['counts']['evaluation_runs']}  delta={after['counts']['evaluation_runs'] - before['counts']['evaluation_runs']} (expected 0)")
        print("  production AI analysis triggered: 0 (no VersionAnalysisService / analysis pipeline import exists in this script)")

        _section("FINAL STATUS: READY_FOR_HUMAN_GT")
        print(f"  C1 status: {c1_status}")
        print(f"  Dataset v2: {dataset_version_id} ({dataset_status})")
        print("  Next allowed action: controlled human ground-truth authoring for Dataset v2, "
              "through the existing reviewer UI, one finding at a time, per the GT authoring "
              "standard already reviewed -- nothing further is auto-approved by this script.")

    except Stop as stop:
        _section("STOPPED")
        print(f"  Reason: {stop}")
        try:
            after = _snapshot(evaluation, contracts, versions) if before is not None else None
        except Exception as snap_exc:  # pragma: no cover -- best-effort final read
            after = None
            print(f"  (could not take a final snapshot: {snap_exc})")
        if before is not None and after is not None:
            _section("PARTIAL STATE AT STOP -- INTEGRITY SNAPSHOT (before/after)")
            _print_snapshot_table(before, after)
        print(f"\n  C1 status at stop: {c1_status}")
        print(f"  Dataset v2 status at stop: {dataset_status}  (dataset_version_id={dataset_version_id})")
        if member_rows:
            print("  Dataset members processed before stop:")
            for row in member_rows:
                print(f"    {row}")
        print("\n  Waiting for explicit approval before any remediation. No further writes attempted.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
