"""Phase E4A/E4G/E4L -- READ-ONLY inventory for benchmark expansion planning.

This script makes NO writes of any kind. It only reads:
  - contracts / contract_versions (the full production inventory)
  - risk_findings (production AI findings -- counted only, NEVER treated as
    ground truth; see the explicit warning in the printed output)
  - evaluation_datasets / evaluation_dataset_members (every benchmark
    dataset that exists, not just the current one)
  - evaluation_ground_truth_findings (every GT finding that exists, for
    every dataset, so the taxonomy review and the C2/C6/C8 preservation
    check both have real numbers)

It calls no AI provider, creates no evaluation run, and modifies nothing.
Safe to re-run as many times as needed.

Usage (from backend/, with your normal venv/credentials):
    python scripts/phase_e4a_inventory.py [--json inventory.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings  # noqa: E402
from app.lexproof.repositories.firestore import FirestoreRepository  # noqa: E402

CURRENT_DATASET_ID = "9106833f-43df-4e0c-a78e-195ce30277af"
KNOWN_SAMPLE_FILENAMES = {
    "CONTRACT_01_NDA_Clean_LowRisk.docx",
    "CONTRACT_02_MSA_MediumRisk.docx",
    "CONTRACT_03_SaaS_HighRisk.docx",
    "CONTRACT_04_PO_Terms_LowRisk.docx",
    "CONTRACT_05_PSA_EscalationTriggers.docx",
    "CONTRACT_06_DPA_ComplianceIssues.docx",
    "CONTRACT_07_Construction_HighRisk.docx",
    "CONTRACT_08_JointVenture_ExecApproval.docx",
}
EXPECTED_CURRENT_COUNTS = {
    "645a2cd6-f436-4e6f-8b14-ac6240d6606a": ("C2", 8),
    "50712c6d-cd84-408e-aac0-9c28ed09f2fe": ("C6", 11),
    "897c9b37-b5a0-4853-b1c6-c42d2cdf1a18": ("C8", 10),
}


def _repos():
    settings = get_settings()
    return {
        "contracts": FirestoreRepository("contracts", settings=settings),
        "versions": FirestoreRepository("contract_versions", settings=settings),
        "risk_findings": FirestoreRepository("risk_findings", settings=settings),
        "datasets": FirestoreRepository("evaluation_datasets", settings=settings),
        "members": FirestoreRepository("evaluation_dataset_members", settings=settings),
        "ground_truth": FirestoreRepository("evaluation_ground_truth_findings", settings=settings),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=None, help="optional path to also dump raw data as JSON")
    args = parser.parse_args()

    repos = _repos()

    contracts = list(repos["contracts"].query())
    versions = list(repos["versions"].query())
    risk_findings = list(repos["risk_findings"].query())
    datasets = list(repos["datasets"].query())
    members = list(repos["members"].query())
    ground_truth = list(repos["ground_truth"].query())

    versions_by_contract: dict[str, list[dict]] = defaultdict(list)
    for v in versions:
        versions_by_contract[str(v.get("contract_id"))].append(v)

    findings_count_by_contract: Counter = Counter(str(f.get("contract_id")) for f in risk_findings)

    print("=" * 100)
    print(f"PRODUCTION CONTRACT INVENTORY -- {len(contracts)} contracts, {len(versions)} versions total")
    print("=" * 100)
    for contract in sorted(contracts, key=lambda c: str(c.get("created_at") or "")):
        cid = str(contract.get("id") or contract.get("contract_id") or "")
        name = contract.get("name") or contract.get("contract_name") or "(no name)"
        cvs = versions_by_contract.get(cid, [])
        current_version_id = contract.get("current_version_id")
        is_known_sample = name in KNOWN_SAMPLE_FILENAMES
        prod_finding_count = findings_count_by_contract.get(cid, 0)
        print(f"\n  contract_id={cid}")
        print(f"    name/filename: {name!r}   known_sample_file: {is_known_sample}")
        print(f"    status: {contract.get('status')}   org_id: {contract.get('org_id')}   owner_id: {contract.get('owner_id')}")
        print(f"    current_version_id: {current_version_id}   version_count: {len(cvs)}")
        print(f"    created_at: {contract.get('created_at')}")
        print(f"    production risk_findings count (NOT ground truth): {prod_finding_count}")
        for v in cvs:
            text = v.get("document_text") or ""
            print(f"      version_id={v.get('id')}  content_hash={v.get('content_hash')}  "
                  f"text_chars={len(text)}  analysis_status={v.get('analysis_status')}  "
                  f"ocr_status={v.get('ocr_status')}  filename={v.get('filename')!r}")

    uploaded_filenames = {str(c.get("name")) for c in contracts}
    missing_samples = KNOWN_SAMPLE_FILENAMES - uploaded_filenames
    print("\n" + "=" * 100)
    print("KNOWN sampleContracts/ FILES NOT YET UPLOADED AS A PRODUCTION CONTRACT RECORD")
    print("=" * 100)
    for name in sorted(missing_samples):
        print(f"  {name}")
    if not missing_samples:
        print("  (none -- all 8 known sample files already have a contract record)")

    print("\n" + "=" * 100)
    print(f"EVALUATION DATASETS -- {len(datasets)} total")
    print("=" * 100)
    members_by_dataset: dict[str, list[dict]] = defaultdict(list)
    for m in members:
        members_by_dataset[str(m.get("dataset_version_id"))].append(m)
    gt_by_dataset: dict[str, list[dict]] = defaultdict(list)
    for g in ground_truth:
        gt_by_dataset[str(g.get("dataset_version_id"))].append(g)

    for dataset in datasets:
        did = str(dataset.get("dataset_version_id"))
        ds_members = members_by_dataset.get(did, [])
        ds_gt = gt_by_dataset.get(did, [])
        print(f"\n  dataset_version_id={did}  name={dataset.get('name')!r}  status={dataset.get('status')}")
        print(f"    ground_truth_source: {dataset.get('ground_truth_source')}   review_type: {dataset.get('review_type')}")
        print(f"    member_count(stored)={dataset.get('contract_count')}  actual_members_found={len(ds_members)}")
        print(f"    gt_count(stored)={dataset.get('ground_truth_finding_count')}  actual_gt_found={len(ds_gt)}")
        for m in ds_members:
            print(f"      member: contract_id={m.get('contract_id')}  version_id={m.get('version_id')}")

    print("\n" + "=" * 100)
    print(f"CURRENT BENCHMARK DATASET ({CURRENT_DATASET_ID}) -- C2/C6/C8 PRESERVATION CHECK")
    print("=" * 100)
    current_gt = gt_by_dataset.get(CURRENT_DATASET_ID, [])
    by_contract: Counter = Counter(str(g.get("contract_id")) for g in current_gt)
    all_ok = True
    for contract_id, (label, expected) in EXPECTED_CURRENT_COUNTS.items():
        actual = by_contract.get(contract_id, 0)
        ok = actual == expected
        all_ok = all_ok and ok
        print(f"  {label} ({contract_id}): expected={expected}  actual={actual}  {'OK' if ok else '<<< MISMATCH -- STOP'}")
    print(f"  TOTAL: expected=29  actual={len(current_gt)}  {'OK' if len(current_gt) == 29 and all_ok else '<<< MISMATCH -- STOP'}")
    finalized_count = sum(1 for g in current_gt if g.get("review_status") == "FINALIZED")
    print(f"  finalized_count={finalized_count} (should equal total if dataset is FINALIZED)")

    print("\n" + "=" * 100)
    print("TAXONOMY REVIEW -- finding_category / clause_reference / expected_severity vocabulary, ALL datasets' GT")
    print("=" * 100)
    category_counts = Counter(str(g.get("finding_category")) for g in ground_truth)
    severity_counts = Counter(str(g.get("expected_severity")) for g in ground_truth)
    print(f"\n  finding_category values ({len(category_counts)} distinct), across {len(ground_truth)} total GT findings:")
    for cat, count in category_counts.most_common():
        print(f"    {count:>3}  {cat}")
    print(f"\n  expected_severity distribution:")
    for sev, count in severity_counts.most_common():
        print(f"    {count:>3}  {sev}")
    empty_recommendation = sum(1 for g in ground_truth if not str(g.get("expected_recommendation") or "").strip())
    empty_evidence = sum(1 for g in ground_truth if not str(g.get("expected_evidence") or "").strip())
    print(f"\n  GT findings with empty expected_recommendation: {empty_recommendation}")
    print(f"  GT findings with empty expected_evidence: {empty_evidence}")
    review_status_counts = Counter(str(g.get("review_status")) for g in ground_truth)
    print(f"\n  review_status distribution (all datasets): {dict(review_status_counts)}")

    if args.json:
        dump = {
            "contracts": contracts,
            "versions": versions,
            "datasets": datasets,
            "members": members,
            "ground_truth_count": len(ground_truth),
            "risk_findings_count_by_contract": dict(findings_count_by_contract),
        }
        Path(args.json).write_text(json.dumps(dump, indent=2, default=str))
        print(f"\nRaw data (excluding full ground_truth records, for brevity) written to {args.json}")


if __name__ == "__main__":
    main()
