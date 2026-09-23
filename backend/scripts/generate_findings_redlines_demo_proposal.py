"""Create one demo redline proposal so the Findings & Redlines page's Redlines
tab has something real to render.

Context: a 2026-09-22 screen-recording review (see the LexProof project's
`claude/findings-redlines-recording-review-2026-09-22.md`) found that the
Findings & Redlines page's Redlines tab was never exercised with live data in
any demo -- none of the existing demo contracts have a persisted redline
proposal. The fetch/render code (GET /api/contracts/{id}/redline-proposals)
is correct either way, but nobody had actually watched it render a populated
list. This script closes that gap the same way the other create_*_demo_fixture.py
scripts in this folder do: by talking to the real Firestore project
(lexproof-afc7c), exactly like the app itself. There is no dry-run mode.

Unlike create_reject_demo_fixture.py, this script does NOT require you to
already know a contract/version/finding id -- it auto-discovers the first
contract that has at least one persisted finding and zero existing redline
proposals, so it's safe to run with no arguments against your current demo
data. It reads that contract's own `owner_id` and creates the proposal as
that owner (ProposalService.create requires created_by == the contract's
owner_id, or an org admin) -- an earlier version of this script defaulted to
a hardcoded "demo-owner-1" actor and hit `PermissionError: You are not
authorized to create a proposal` on contracts owned by someone else. Reruns
are safe: it never touches a contract that already has a proposal.

Usage:
    python scripts/generate_findings_redlines_demo_proposal.py [actor_user_id]

    actor_user_id -- optional override. If omitted, the script uses the
                     candidate contract's own owner_id, which is always
                     authorized to create a proposal on it.

Prints the created proposal_id, contract_id, and the exact frontend URL to
open and confirm on the Redlines tab.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.repositories.firestore import FirestoreRepository  # noqa: E402
from app.lexproof.services.redline_proposals import ProposalService, RedlineProposalError  # noqa: E402


def build_proposed_text(finding: dict) -> str:
    recommendation = (finding.get("recommendation") or "").strip()
    title = (finding.get("title") or "this clause").strip()
    if recommendation:
        return recommendation
    return f"Revise the clause addressing \"{title}\" to remediate the risk identified by AI analysis."


def main() -> None:
    actor_override = sys.argv[1] if len(sys.argv) > 1 else None

    contracts_repo = FirestoreRepository("contracts")
    findings_repo = FirestoreRepository("risk_findings")
    proposals_repo = FirestoreRepository("redline_proposals")

    print("Scanning findings for a contract with no existing redline proposal...")
    all_findings = findings_repo.query(limit=500)
    if not all_findings:
        raise SystemExit("No findings found in risk_findings -- analyze a contract first.")

    by_contract: dict[str, list[dict]] = {}
    for finding in all_findings:
        contract_id = finding.get("contract_id")
        if not contract_id:
            continue
        by_contract.setdefault(str(contract_id), []).append(finding)

    for contract_id, findings in by_contract.items():
        existing = proposals_repo.query(equal={"contract_id": contract_id}, limit=1)
        if existing:
            continue
        finding = findings[0]
        version_id = finding.get("version_id")
        finding_id = finding.get("finding_id") or finding.get("id")
        if not version_id or not finding_id:
            continue

        contract = contracts_repo.get(contract_id)
        if not contract:
            continue
        actor_id = actor_override or contract.get("owner_id")
        if not actor_id:
            print(f"Skipping {contract_id} (no owner_id on the contract and no actor override given); trying next contract...")
            continue

        proposed_text = build_proposed_text(finding)
        service = ProposalService(contracts=contracts_repo, findings=findings_repo, proposals=proposals_repo)
        try:
            proposal = service.create(contract_id, version_id, finding_id, proposed_text, actor_id)
        except (RedlineProposalError, PermissionError) as exc:
            print(f"Skipping {contract_id} ({exc}); trying next contract...")
            continue

        print()
        print("Created redline proposal:")
        print("  proposal_id:", proposal["proposal_id"])
        print("  contract_id:", contract_id)
        print("  source_version_id:", version_id)
        print("  finding_id:", finding_id)
        print("  actor_id (contract owner):", actor_id)
        print("  status:", proposal.get("status"))
        print("  proposed_text:", proposed_text)
        print()
        print("Open this in the app to confirm the Redlines tab renders it:")
        print(f"  /dashboard/ai-analysis/findings?contract_id={contract_id}  (then click the \"Redlines\" tab)")
        return

    raise SystemExit(
        "Every contract with findings already has a redline proposal, or none had a usable owner_id -- "
        "nothing to do. Pass a specific actor_user_id if you want to force one on a particular contract."
    )


if __name__ == "__main__":
    main()
