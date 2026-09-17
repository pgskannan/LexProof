"""Create one clean, dedicated Reject Demo fixture.

Hardening item #4 ("Build/freeze one pristine demo dataset") calls for four
separate, non-overlapping demo fixtures: the primary Demo Contract, a Tamper
Demo (see tamper_demo.py / restore_demo_evidence.py / create_tamper_demo_fixture.py),
a Batch Anchor Demo (create_merkle_batch_demo_anchor.py), and a Reject Demo --
this script. Do not mix these datasets: this script creates a brand-new
redline proposal on a contract/version/finding of your choosing and reviews
it REJECTED, so a presenter has a clean, dedicated example of the reject path
that can never accidentally become publishable (a REJECTED proposal's
published_version_id stays null forever -- see
services/redline_proposals.py's publish(), which requires status == "APPROVED").

This talks to your real Firestore (and, indirectly, real Gemini/Sepolia
config via get_settings()) exactly like the app itself -- there is no dry-run
mode. Point it at a contract/version/finding that already exists (e.g. from
the primary Demo Contract's V1, or any other seeded contract) rather than
your actual demo's own pending proposal, so this fixture stays visibly
separate from the rest of the demo state.

Usage:
    python scripts/create_reject_demo_fixture.py <contract_id> <version_id> <finding_id> <actor_user_id> <reviewer_user_id>

    contract_id       -- an existing contract you own
    version_id        -- an existing version of that contract (its current version_id)
    finding_id        -- an existing finding on that version to draft a redline against
    actor_user_id     -- the uid that "drafts" the proposal (must own the contract)
    reviewer_user_id  -- the uid that reviews and rejects it (must NOT be actor_user_id --
                         the workflow engine enforces separation of duties)

Prints the created proposal_id and the review result for reference in the
demo script/documentation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.services.redline_proposals import ProposalService  # noqa: E402

REJECT_DEMO_PROPOSED_TEXT = (
    "Total liability shall be capped at the greater of $50,000 or twelve (12) "
    "months of fees paid in the preceding year."
)

REJECT_DEMO_COMMENT = (
    "Reject Demo fixture (hardening item #4): rejected on purpose to "
    "demonstrate the redline review workflow's reject path. This proposal is "
    "a dedicated fixture, kept deliberately separate from the primary Demo "
    "Contract's own approved/published proposal -- do not approve or publish it."
)


def main() -> None:
    if len(sys.argv) != 6:
        raise SystemExit(
            "Usage: python scripts/create_reject_demo_fixture.py "
            "<contract_id> <version_id> <finding_id> <actor_user_id> <reviewer_user_id>"
        )
    contract_id, version_id, finding_id, actor_id, reviewer_id = sys.argv[1:6]
    if actor_id == reviewer_id:
        raise SystemExit(
            "actor_user_id and reviewer_user_id must be different accounts -- "
            "the workflow engine's separation-of-duties rule forbids a single "
            "user both drafting and reviewing the same proposal, same as it "
            "would for a real reviewer."
        )

    service = ProposalService()

    proposal = service.create(contract_id, version_id, finding_id, REJECT_DEMO_PROPOSED_TEXT, actor_id)
    print("Created proposal_id:", proposal["proposal_id"])
    print("  contract_id:", proposal.get("contract_id"))
    print("  source_version_id:", proposal.get("source_version_id"))
    print("  status (pre-review):", proposal.get("status"))

    review = service.review(proposal["proposal_id"], "REJECTED", reviewer_id, REJECT_DEMO_COMMENT)
    print()
    print("Reviewed:")
    print("  decision:", review.get("decision"))
    print("  reviewer_id:", reviewer_id)
    print("  comment:", REJECT_DEMO_COMMENT)

    final = service.get(proposal["proposal_id"], actor_id)
    print()
    print("Final proposal state:")
    print("  status:", final.get("status"))
    print("  published_version_id:", final.get("published_version_id"))
    print()
    print("This proposal is REJECTED. Its published_version_id stays null "
          "permanently -- publish() requires status == 'APPROVED', so this "
          "fixture can never accidentally be published in a live demo.")
    print("Reference it in the demo script by proposal_id:", proposal["proposal_id"])


if __name__ == "__main__":
    main()
