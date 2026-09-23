"""Create deterministic demo scenarios through the real LexProof workflow.

This script provisions two independent, idempotent fixtures against the
SAME dedicated demo organization ("lexproof-demo"):

  1. create_pending_review_fixture() -- the original Phase-era fixture: a
     contract owner creates a redline proposal from a persisted finding and
     it is immediately submitted for review (workflow instance state
     "in_review"). No review decision is recorded. This is UNCHANGED from
     the original script and is preserved so any existing consumer of it
     keeps working exactly as before.

  2. create_golden_path_draft_fixture() -- added for Phase 3J-B. Seeds a
     SEPARATE, dedicated contract/version/finding/proposal that is left in
     the workflow's initial "draft" state (empty proposed_text -> no
     auto-submit -- see services/redline_proposals.py's create(), and
     tests/test_redline_proposals.py::test_draft_proposal_has_no_sla_due_date
     for the same empty-proposed_text -> DRAFT behavior this relies on).
     This gives the future golden-path E2E test (Phase 3K, not built here)
     a guaranteed-clean, always-reproducible starting point: contract
     owner has NOT yet submitted for review, so "Submit for review" is the
     very first action available. It intentionally uses its own
     contract/version/finding ids, distinct from the pending-review
     fixture's, so this phase never touches or reinterprets that older
     fixture's data -- both are safe to run any number of times, in any
     order, without interfering with each other.

Both fixtures reuse the same four deterministic, role-distinct identities
in "lexproof-demo" (demo-owner-1 / contract_owner, demo-reviewer-1 /
reviewer, demo-approver-1 / approver, demo-admin-1 / admin) -- one identity
per workflow role, as already established by the original fixture. No new
identity, and no second demo organization, is introduced.

Usage:
    python scripts/create_approval_demo_fixture.py                 # both fixtures (default, original behavior + new)
    python scripts/create_approval_demo_fixture.py --fixture golden-path     # only the Phase 3J-B draft fixture
    python scripts/create_approval_demo_fixture.py --fixture golden-path --reset
        # delete the golden-path proposal/workflow/reviews (only) and re-seed DRAFT.
        # Needed after the golden-path E2E test advances the proposal. Does not
        # touch the pending-review fixture.
    python scripts/create_approval_demo_fixture.py --fixture pending-review --reset
        # delete the pending-review proposal/workflow/reviews and re-seed PROPOSED.
        # Needed after that proposal was approved through the app. Does not
        # touch golden-path or duplicate-approval fixtures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.redline_proposals import ProposalService

ORG_ID = "lexproof-demo"
CONTRACT_ID = "demo-lexproof-pending-master-services-agreement"
VERSION_ID = "demo-lexproof-pending-master-services-agreement-v1"
FINDING_ID = "demo-lexproof-pending-liability-cap-finding"

OWNER_ID = "demo-owner-1"
REVIEWER_ID = "demo-reviewer-1"
APPROVER_ID = "demo-approver-1"
ADMIN_ID = "demo-admin-1"
AUTHENTICATED_USER_ID = "VJEexqdPVwYJ73D6vShQ75DSGdZ2"
AUTHENTICATED_USER_EMAIL = "pgskannan@gmail.com"

CONTRACT_NAME = "Demo Master Services Agreement"
PROPOSED_TEXT = (
    "The total liability cap for any claim shall be the greater of $500,000 or "
    "twelve (12) months of fees paid in the preceding year."
)

# Phase 3J-B: a second, independent deterministic contract dedicated to the
# golden-path demo. Distinct ids from the pending-review fixture above on
# purpose -- see module docstring.
GOLDEN_PATH_CONTRACT_ID = "demo-golden-path-master-services-agreement"
GOLDEN_PATH_VERSION_ID = "demo-golden-path-master-services-agreement-v1"
GOLDEN_PATH_FINDING_ID = "demo-golden-path-liability-cap-finding"
GOLDEN_PATH_CONTRACT_NAME = "Demo Golden Path Master Services Agreement"


def _document_text() -> str:
    return """MASTER SERVICES AGREEMENT

This Master Services Agreement (this \"Agreement\") is entered into by and between
Acme Advisory Group and Northwind Systems, Inc. (the \"Parties\").

1. SERVICES. Provider will deliver the professional services described in the
Statement of Work.

2. LIABILITY CAP. The total liability cap for any claim is $100,000.

3. TERM. This Agreement will continue until terminated in accordance with Section 7.

4. CONFIDENTIALITY. Each Party shall maintain the confidentiality of non-public
information disclosed in connection with this Agreement.

5. PAYMENT. Customer will pay Fees within thirty (30) days after invoice.
"""


def _finding_record() -> dict:
    return {
        "id": FINDING_ID,
        "org_id": ORG_ID,
        "contract_id": CONTRACT_ID,
        "version_id": VERSION_ID,
        "title": "Liability cap is too low",
        "severity": "high",
        "description": "The liability cap is below a commercially reasonable threshold and leaves the customer exposed to outsized risk.",
        "recommendation": "Increase the cap to a more balanced level and align it with a market standard.",
        "evidence_quote": "The total liability cap for any claim is $100,000.",
        "evidence": {
            "text": "The total liability cap for any claim is $100,000.",
            "clause": "LIABILITY CAP",
        },
        "created_at": "2026-09-13T09:00:00Z",
    }


def _version_record() -> dict:
    return {
        "id": VERSION_ID,
        "org_id": ORG_ID,
        "contract_id": CONTRACT_ID,
        "owner_id": OWNER_ID,
        "version_number": 1,
        "filename": "demo-master-services-agreement.txt",
        "content_type": "text/plain",
        "document_text": _document_text(),
        "analysis_status": "complete",
        "created_at": "2026-09-13T09:00:00Z",
        "created_by": OWNER_ID,
    }


def _contract_record() -> dict:
    return {
        "id": CONTRACT_ID,
        "org_id": ORG_ID,
        "owner_id": OWNER_ID,
        "name": CONTRACT_NAME,
        "status": "uploaded",
        "current_version_id": VERSION_ID,
        "created_at": "2026-09-13T08:00:00Z",
        "updated_at": "2026-09-13T09:00:00Z",
    }


def _ensure_org(orgs: OrganizationService) -> None:
    org = orgs.orgs.get(ORG_ID)
    if not org:
        orgs.create_org(
            CONTRACT_NAME,
            ADMIN_ID,
            org_id=ORG_ID,
            creator_email="demo-admin@lexproof.local",
            creator_display_name="Demo Admin",
            roles=["admin"],
        )
    for user_id, roles in {
        OWNER_ID: ["contract_owner"],
        REVIEWER_ID: ["reviewer"],
        APPROVER_ID: ["approver"],
        ADMIN_ID: ["admin"],
    }.items():
        orgs.ensure_member(ORG_ID, user_id, roles, email=f"{user_id}@lexproof.local", invited_by=ADMIN_ID)
    orgs.ensure_member(
        ORG_ID,
        AUTHENTICATED_USER_ID,
        ["admin"],
        email=AUTHENTICATED_USER_EMAIL,
        invited_by=ADMIN_ID,
    )


def _ensure_contract_and_version() -> None:
    contracts = FirestoreRepository("contracts")
    versions = FirestoreRepository("contract_versions")
    if not contracts.get(CONTRACT_ID):
        contracts.set(CONTRACT_ID, _contract_record())
    if not versions.get(VERSION_ID):
        versions.set(VERSION_ID, _version_record())


def _ensure_finding() -> None:
    findings = FirestoreRepository("risk_findings")
    if not findings.get(FINDING_ID):
        findings.set(FINDING_ID, _finding_record())


def _existing_proposal(proposals: FirestoreRepository | None = None) -> dict | None:
    proposals = proposals or FirestoreRepository("redline_proposals")
    for proposal in proposals.stream():
        if proposal.get("contract_id") == CONTRACT_ID and proposal.get("finding_id") == FINDING_ID:
            return proposal
    return None


def create_pending_review_fixture(orgs: OrganizationService) -> None:
    """Original Phase-era fixture. Unchanged behavior: creates (or reuses)
    ORG_ID/CONTRACT_ID's redline proposal, submitted for review. Left
    exactly as it was before Phase 3J-B so nothing that already depends on
    it changes."""
    _ensure_org(orgs)
    _ensure_contract_and_version()
    _ensure_finding()

    service = ProposalService(organizations=orgs)
    existing = _existing_proposal(service.proposals)
    if existing:
        proposal = existing
    else:
        proposal = service.create(CONTRACT_ID, VERSION_ID, FINDING_ID, PROPOSED_TEXT, OWNER_ID)

    final = service.get(proposal["proposal_id"], OWNER_ID)
    authenticated_view = service.get(proposal["proposal_id"], AUTHENTICATED_USER_ID)
    instance = service.workflow.get_instance(final["workflow_instance_id"])
    contract = service.contracts.get(CONTRACT_ID)
    version = service.versions.get(VERSION_ID)
    finding = service.findings.get(FINDING_ID)
    approver = orgs.get_active_member(ORG_ID, APPROVER_ID)
    authenticated_member = orgs.get_active_member(ORG_ID, AUTHENTICATED_USER_ID)
    review_repo = FirestoreRepository("redline_reviews")
    decisions = [
        review
        for review in review_repo.stream()
        if review.get("proposal_id") == final["proposal_id"]
    ]
    if final.get("status") != "PROPOSED":
        raise RuntimeError(
            f"Expected proposal status PROPOSED, got {final.get('status')!r}. "
            "This fixture's proposal has moved past its original PROPOSED state "
            "(e.g. reviewed/approved/rejected/published through the app since it "
            "was last seeded). Re-run with --fixture pending-review --reset to "
            "delete the stale proposal/workflow/reviews and seed a fresh PROPOSED "
            "in_review instance. --reset does not touch the golden-path or "
            "duplicate-approval fixtures."
        )
    if not contract or contract.get("id") not in {None, CONTRACT_ID}:
        raise RuntimeError(f"Contract not found: {CONTRACT_ID}")
    if not version or version.get("analysis_status") != "complete":
        raise RuntimeError("Expected a completed-analysis contract version")
    if not finding or finding.get("contract_id") != CONTRACT_ID or finding.get("version_id") != VERSION_ID:
        raise RuntimeError("Expected a finding linked to the seeded contract and completed version")
    if instance.get("current_state") != "in_review":
        raise RuntimeError(f"Expected workflow state in_review, got {instance.get('current_state')!r}")
    if "reviewer" not in (instance.get("available_roles") or []):
        raise RuntimeError("Expected the workflow instance to be assigned to the reviewer role")
    if not approver or APPROVER_ID not in (approver.get("user_id"), approver.get("id")):
        raise RuntimeError(f"Approver membership not found: {APPROVER_ID}")
    if "approver" not in (approver.get("roles") or []):
        raise RuntimeError(f"User is not assigned the approver role: {APPROVER_ID}")
    if not authenticated_member or authenticated_view.get("contract_id") != CONTRACT_ID:
        raise RuntimeError("Authenticated demo user cannot access the seeded contract")
    if not set(authenticated_member.get("roles") or []).intersection({"reviewer", "admin"}):
        raise RuntimeError("Authenticated demo user lacks the role for the initial in_review transition")
    if decisions:
        raise RuntimeError(f"Unexpected approval decision recorded: {decisions!r}")
    if final.get("published_version_id") is not None:
        raise RuntimeError("Expected no published version")
    if final.get("status") == "APPROVED" or instance.get("current_state") == "approved":
        raise RuntimeError("Fixture must not create an approved state")

    proposal_state = {
        "proposal_id": final["proposal_id"],
        "status": final.get("status"),
        "contract_id": final.get("contract_id"),
        "finding_id": final.get("finding_id"),
        "workflow_instance_id": final.get("workflow_instance_id"),
    }
    workflow_state = {
        "instance_id": instance.get("instance_id"),
        "current_state": instance.get("current_state"),
        "status": instance.get("status"),
        "available_roles": instance.get("available_roles"),
    }
    approval_state = {
        "decision": None,
        "recorded_reviews": decisions,
    }
    approver_state = {
        "user_id": APPROVER_ID,
        "roles": approver.get("roles"),
        "status": approver.get("status"),
    }
    authenticated_user_state = {
        "user_id": AUTHENTICATED_USER_ID,
        "email": AUTHENTICATED_USER_EMAIL,
        "roles": authenticated_member.get("roles"),
        "status": authenticated_member.get("status"),
        "contract_access": authenticated_view.get("contract_id") == CONTRACT_ID,
    }
    print("[pending-review] ORG_ID:", ORG_ID)
    print("[pending-review] CONTRACT_ID:", CONTRACT_ID)
    print("[pending-review] VERSION_ID:", VERSION_ID)
    print("[pending-review] FINDING_ID:", FINDING_ID)
    print("[pending-review] PROPOSAL:", proposal_state)
    print("[pending-review] WORKFLOW:", workflow_state)
    print("[pending-review] REVIEW_DECISION: pending")
    print("[pending-review] APPROVAL_INSTANCE:", instance.get("instance_id"))
    print("[pending-review] APPROVER:", approver_state)
    print("[pending-review] AUTHENTICATED_USER:", authenticated_user_state)
    print("[pending-review] PUBLISHED_VERSION_ID:", final.get("published_version_id"))
    print("[pending-review] APPROVAL_STATE:", approval_state)
    print("[pending-review] READY_FOR_MANUAL_REVIEW: yes")


# --- Phase 3J-B: deterministic golden-path draft fixture -------------------


def _golden_path_finding_record() -> dict:
    return {
        "id": GOLDEN_PATH_FINDING_ID,
        "org_id": ORG_ID,
        "contract_id": GOLDEN_PATH_CONTRACT_ID,
        "version_id": GOLDEN_PATH_VERSION_ID,
        "title": "Liability cap is too low",
        "severity": "high",
        "description": "The liability cap is below a commercially reasonable threshold and leaves the customer exposed to outsized risk.",
        "recommendation": "Increase the cap to a more balanced level and align it with a market standard.",
        "evidence_quote": "The total liability cap for any claim is $100,000.",
        "evidence": {
            "text": "The total liability cap for any claim is $100,000.",
            "clause": "LIABILITY CAP",
        },
        "created_at": "2026-09-17T00:00:00Z",
    }


def _golden_path_version_record() -> dict:
    return {
        "id": GOLDEN_PATH_VERSION_ID,
        "org_id": ORG_ID,
        "contract_id": GOLDEN_PATH_CONTRACT_ID,
        "owner_id": OWNER_ID,
        "version_number": 1,
        "filename": "demo-golden-path-master-services-agreement.txt",
        "content_type": "text/plain",
        "document_text": _document_text(),
        "analysis_status": "complete",
        "created_at": "2026-09-17T00:00:00Z",
        "created_by": OWNER_ID,
    }


def _golden_path_contract_record() -> dict:
    return {
        "id": GOLDEN_PATH_CONTRACT_ID,
        "org_id": ORG_ID,
        "owner_id": OWNER_ID,
        "name": GOLDEN_PATH_CONTRACT_NAME,
        "status": "uploaded",
        "current_version_id": GOLDEN_PATH_VERSION_ID,
        "created_at": "2026-09-17T00:00:00Z",
        "updated_at": "2026-09-17T00:00:00Z",
    }


def _ensure_golden_path_contract_and_version(contracts: FirestoreRepository, versions: FirestoreRepository) -> None:
    if not contracts.get(GOLDEN_PATH_CONTRACT_ID):
        contracts.set(GOLDEN_PATH_CONTRACT_ID, _golden_path_contract_record())
    if not versions.get(GOLDEN_PATH_VERSION_ID):
        versions.set(GOLDEN_PATH_VERSION_ID, _golden_path_version_record())


def _ensure_golden_path_finding(findings: FirestoreRepository) -> None:
    if not findings.get(GOLDEN_PATH_FINDING_ID):
        findings.set(GOLDEN_PATH_FINDING_ID, _golden_path_finding_record())


def _existing_golden_path_proposal(proposals: FirestoreRepository) -> dict | None:
    for proposal in proposals.stream():
        if proposal.get("contract_id") == GOLDEN_PATH_CONTRACT_ID and proposal.get("finding_id") == GOLDEN_PATH_FINDING_ID:
            return proposal
    return None


def _stream_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("proposal_id") or record.get("review_id") or record.get("event_id") or "")


def reset_golden_path_workflow_state(service: ProposalService) -> dict[str, Any]:
    """Delete only the golden-path proposal's workflow artifacts so the
    fixture can be re-seeded at DRAFT.

    Explicit and opt-in: the default seed path still refuses to overwrite an
    advanced proposal. This does not touch the pending-review fixture, org
    membership, or the golden-path contract/version/finding documents.
    Extra published versions for the golden-path contract (if any) are
    removed and current_version_id is restored to the seeded v1.
    """
    deleted: dict[str, Any] = {
        "proposals": [],
        "reviews": [],
        "audits": [],
        "instances": [],
        "history_events": 0,
        "extra_versions": [],
    }
    existing = _existing_golden_path_proposal(service.proposals)
    if not existing:
        print("[golden-path] RESET: no existing proposal to delete")
        return deleted

    proposal_id = _stream_id(existing)
    instance_id = existing.get("workflow_instance_id")

    for review in list(service.reviews.stream()):
        if review.get("proposal_id") == proposal_id:
            review_id = _stream_id(review)
            service.reviews.delete(review_id)
            deleted["reviews"].append(review_id)

    for audit in list(service.publication_audits.stream()):
        if audit.get("proposal_id") == proposal_id:
            audit_id = _stream_id(audit)
            service.publication_audits.delete(audit_id)
            deleted["audits"].append(audit_id)

    if instance_id:
        history = service.workflow.history(str(instance_id))
        for event in list(history.stream()):
            history.delete(_stream_id(event))
            deleted["history_events"] += 1
        service.workflow.instances.delete(str(instance_id))
        deleted["instances"].append(str(instance_id))

    service.proposals.delete(proposal_id)
    deleted["proposals"].append(proposal_id)

    for version in list(service.versions.stream()):
        version_id = _stream_id(version)
        if version.get("contract_id") == GOLDEN_PATH_CONTRACT_ID and version_id != GOLDEN_PATH_VERSION_ID:
            service.versions.delete(version_id)
            deleted["extra_versions"].append(version_id)

    contract = service.contracts.get(GOLDEN_PATH_CONTRACT_ID)
    if contract and contract.get("current_version_id") != GOLDEN_PATH_VERSION_ID:
        service.contracts.set(
            GOLDEN_PATH_CONTRACT_ID,
            {**contract, "current_version_id": GOLDEN_PATH_VERSION_ID, "status": "uploaded"},
            merge=True,
        )

    print("[golden-path] RESET deleted:", deleted)
    return deleted


def reset_pending_review_workflow_state(service: ProposalService) -> dict[str, Any]:
    """Delete only the pending-review proposal's workflow artifacts so the
    fixture can be re-seeded at PROPOSED.

    Explicit and opt-in: the default seed path still refuses to overwrite an
    advanced proposal. The negative-security E2E tests (4A/4B) require this
    fixture to still be in_review / PROPOSED; they never themselves approve
    it, but a prior human or E2E review can. Does not touch golden-path or
    duplicate-approval fixtures.
    """
    deleted: dict[str, Any] = {
        "proposals": [],
        "reviews": [],
        "audits": [],
        "instances": [],
        "history_events": 0,
        "extra_versions": [],
    }
    existing = _existing_proposal(service.proposals)
    if not existing:
        print("[pending-review] RESET: no existing proposal to delete")
        return deleted

    proposal_id = _stream_id(existing)
    instance_id = existing.get("workflow_instance_id")

    for review in list(service.reviews.stream()):
        if review.get("proposal_id") == proposal_id:
            review_id = _stream_id(review)
            service.reviews.delete(review_id)
            deleted["reviews"].append(review_id)

    for audit in list(service.publication_audits.stream()):
        if audit.get("proposal_id") == proposal_id:
            audit_id = _stream_id(audit)
            service.publication_audits.delete(audit_id)
            deleted["audits"].append(audit_id)

    if instance_id:
        history = service.workflow.history(str(instance_id))
        for event in list(history.stream()):
            history.delete(_stream_id(event))
            deleted["history_events"] += 1
        service.workflow.instances.delete(str(instance_id))
        deleted["instances"].append(str(instance_id))

    service.proposals.delete(proposal_id)
    deleted["proposals"].append(proposal_id)

    for version in list(service.versions.stream()):
        version_id = _stream_id(version)
        if version.get("contract_id") == CONTRACT_ID and version_id != VERSION_ID:
            service.versions.delete(version_id)
            deleted["extra_versions"].append(version_id)

    contract = service.contracts.get(CONTRACT_ID)
    if contract and contract.get("current_version_id") != VERSION_ID:
        service.contracts.set(
            CONTRACT_ID,
            {**contract, "current_version_id": VERSION_ID, "status": "uploaded"},
            merge=True,
        )

    print("[pending-review] RESET deleted:", deleted)
    return deleted


def create_golden_path_draft_fixture(
    orgs: OrganizationService,
    *,
    contracts: FirestoreRepository | None = None,
    versions: FirestoreRepository | None = None,
    findings: FirestoreRepository | None = None,
    service: ProposalService | None = None,
) -> dict[str, Any]:
    """Idempotently seed the Phase 3J-B golden-path demo: one contract, one
    version, one finding, and ONE redline proposal left at the workflow's
    initial "draft" state (created with an empty proposed_text, so
    ProposalService.create() never auto-submits it -- see
    services/redline_proposals.py's create() and the existing
    test_draft_proposal_has_no_sla_due_date test for the same behavior).

    Repositories are injectable (default: real Firestore) so this is unit
    testable offline against FakeRepository, the same pattern already used
    by ProposalService/OrganizationService and tests/test_redline_proposals.py.

    Running this twice performs zero additional writes on the second call:
    every step is a `.get()`-before-`.set()` guard, and the workflow engine's
    own start_instance()/find_instance() is itself idempotent per
    (org_id, entity_type, entity_id).
    """
    contracts = contracts or FirestoreRepository("contracts")
    versions = versions or FirestoreRepository("contract_versions")
    findings = findings or FirestoreRepository("risk_findings")

    _ensure_org(orgs)
    _ensure_golden_path_contract_and_version(contracts, versions)
    _ensure_golden_path_finding(findings)

    service = service or ProposalService(
        contracts=contracts, versions=versions, findings=findings, organizations=orgs,
    )
    existing = _existing_golden_path_proposal(service.proposals)
    if existing:
        proposal = existing
    else:
        # Empty proposed_text -> ProposalService.create() sets status="DRAFT"
        # and leaves the workflow instance at its initial "draft" state
        # (no auto submit-for-review). This IS the deterministic starting
        # point the golden-path E2E test needs.
        proposal = service.create(
            GOLDEN_PATH_CONTRACT_ID, GOLDEN_PATH_VERSION_ID, GOLDEN_PATH_FINDING_ID, "", OWNER_ID,
        )

    final = service.get(proposal["proposal_id"], OWNER_ID)
    instance = service.workflow.get_instance(final["workflow_instance_id"])
    contract = service.contracts.get(GOLDEN_PATH_CONTRACT_ID)
    version = service.versions.get(GOLDEN_PATH_VERSION_ID)
    finding = service.findings.get(GOLDEN_PATH_FINDING_ID)
    owner = orgs.get_active_member(ORG_ID, OWNER_ID)
    reviewer = orgs.get_active_member(ORG_ID, REVIEWER_ID)
    approver = orgs.get_active_member(ORG_ID, APPROVER_ID)
    review_repo = service.reviews
    decisions = [
        review for review in review_repo.stream() if review.get("proposal_id") == final["proposal_id"]
    ]

    # -- Deterministic starting-state checks (fail loudly rather than hand
    # back an ambiguous/advanced state; see create_pending_review_fixture's
    # equivalent RuntimeError for why this fixture never silently resets
    # state that has moved on since it was last seeded). --
    if final.get("status") != "DRAFT":
        raise RuntimeError(
            f"Expected golden-path proposal status DRAFT, got {final.get('status')!r}. "
            "The golden-path proposal has moved past its initial draft state "
            "(e.g. submitted/reviewed/published since it was last seeded). This "
            "fixture never silently resets workflow state. Re-run with "
            f"--fixture golden-path --reset to delete the stale "
            f"{GOLDEN_PATH_CONTRACT_ID}/{GOLDEN_PATH_FINDING_ID} proposal/"
            "workflow/reviews and seed a fresh DRAFT. --reset does not touch "
            "the pending-review fixture."
        )
    if instance.get("current_state") != "draft":
        raise RuntimeError(f"Expected workflow state draft, got {instance.get('current_state')!r}")
    if instance.get("status") != "in_progress":
        raise RuntimeError(f"Expected workflow instance status in_progress, got {instance.get('status')!r}")
    if "contract_owner" not in (instance.get("available_roles") or []):
        raise RuntimeError("Expected 'Submit for review' (contract_owner) to be the available transition")
    if not contract or contract.get("owner_id") != OWNER_ID:
        raise RuntimeError(f"Golden-path contract owner is not {OWNER_ID!r}: {contract}")
    if not version or version.get("analysis_status") != "complete":
        raise RuntimeError("Expected a completed-analysis contract version")
    if not finding or finding.get("contract_id") != GOLDEN_PATH_CONTRACT_ID or finding.get("version_id") != GOLDEN_PATH_VERSION_ID:
        raise RuntimeError("Expected a finding linked to the golden-path contract and completed version")
    if not owner or "contract_owner" not in (owner.get("roles") or []):
        raise RuntimeError(f"Contract owner role missing for {OWNER_ID}")
    if not reviewer or "reviewer" not in (reviewer.get("roles") or []):
        raise RuntimeError(f"Reviewer role missing for {REVIEWER_ID}")
    if not approver or "approver" not in (approver.get("roles") or []):
        raise RuntimeError(f"Approver role missing for {APPROVER_ID}")
    if len({OWNER_ID, REVIEWER_ID, APPROVER_ID}) != 3:
        raise RuntimeError("Contract owner, reviewer, and approver must be three distinct identities")
    if decisions:
        raise RuntimeError(f"Unexpected review decision recorded on a draft proposal: {decisions!r}")
    if final.get("published_version_id") is not None:
        raise RuntimeError("Expected no published version on a draft proposal")

    summary = {
        "org_id": ORG_ID,
        "contract_id": GOLDEN_PATH_CONTRACT_ID,
        "version_id": GOLDEN_PATH_VERSION_ID,
        "finding_id": GOLDEN_PATH_FINDING_ID,
        "proposal_id": final["proposal_id"],
        "proposal_status": final.get("status"),
        "workflow_instance_id": instance.get("instance_id"),
        "workflow_state": instance.get("current_state"),
        "available_roles": instance.get("available_roles"),
        "contract_owner": OWNER_ID,
        "reviewer": REVIEWER_ID,
        "approver": APPROVER_ID,
        "admin": ADMIN_ID,
        "published_version_id": final.get("published_version_id"),
    }
    print("[golden-path] ORG_ID:", summary["org_id"])
    print("[golden-path] CONTRACT_ID:", summary["contract_id"])
    print("[golden-path] VERSION_ID:", summary["version_id"])
    print("[golden-path] FINDING_ID:", summary["finding_id"])
    print("[golden-path] PROPOSAL_ID:", summary["proposal_id"])
    print("[golden-path] PROPOSAL_STATUS:", summary["proposal_status"])
    print("[golden-path] WORKFLOW_INSTANCE_ID:", summary["workflow_instance_id"])
    print("[golden-path] WORKFLOW_STATE:", summary["workflow_state"])
    print("[golden-path] AVAILABLE_ROLES:", summary["available_roles"])
    print("[golden-path] CONTRACT_OWNER:", summary["contract_owner"])
    print("[golden-path] REVIEWER:", summary["reviewer"])
    print("[golden-path] APPROVER:", summary["approver"])
    print("[golden-path] ADMIN:", summary["admin"])
    print("[golden-path] PUBLISHED_VERSION_ID:", summary["published_version_id"])
    print("[golden-path] READY_FOR_SUBMIT_FOR_REVIEW: yes")
    return summary


# Phase (audit follow-up): a THIRD dedicated fixture, distinct ids from both
# the pending-review and golden-path fixtures above, seeded all the way to a
# real APPROVED state through the real ProposalService/workflow engine (not
# hand-written Firestore documents). This exists specifically so an E2E
# negative test can prove "duplicate approval is rejected" without depending
# on the golden-path test having already run and advanced its own proposal
# to APPROVED first (that would be a test-ordering dependency -- see the E2E
# workflow audit's Phase 8 test-isolation note). Once APPROVED, a proposal is
# stable forever under repeated re-runs of this fixture (ProposalService.
# review() refuses a second decision with FinalDecisionError, so this
# function deliberately checks-before-reviewing rather than calling review()
# unconditionally).

DUPLICATE_APPROVAL_CONTRACT_ID = "demo-duplicate-approval-master-services-agreement"
DUPLICATE_APPROVAL_VERSION_ID = "demo-duplicate-approval-master-services-agreement-v1"
DUPLICATE_APPROVAL_FINDING_ID = "demo-duplicate-approval-liability-cap-finding"
DUPLICATE_APPROVAL_CONTRACT_NAME = "Demo Duplicate-Approval Master Services Agreement"
DUPLICATE_APPROVAL_PROPOSED_TEXT = (
    "The total liability cap for any claim shall be the greater of $600,000 or "
    "fifteen (15) months of fees paid in the preceding year."
)


def _duplicate_approval_contract_record() -> dict:
    return {
        "id": DUPLICATE_APPROVAL_CONTRACT_ID,
        "org_id": ORG_ID,
        "owner_id": OWNER_ID,
        "name": DUPLICATE_APPROVAL_CONTRACT_NAME,
        "status": "uploaded",
        "current_version_id": DUPLICATE_APPROVAL_VERSION_ID,
        "created_at": "2026-09-18T00:00:00Z",
        "updated_at": "2026-09-18T00:00:00Z",
    }


def _duplicate_approval_version_record() -> dict:
    return {
        "id": DUPLICATE_APPROVAL_VERSION_ID,
        "org_id": ORG_ID,
        "contract_id": DUPLICATE_APPROVAL_CONTRACT_ID,
        "owner_id": OWNER_ID,
        "version_number": 1,
        "filename": "demo-duplicate-approval-master-services-agreement.txt",
        "content_type": "text/plain",
        "document_text": _document_text(),
        "analysis_status": "complete",
        "created_at": "2026-09-18T00:00:00Z",
    }


def _duplicate_approval_finding_record() -> dict:
    return {
        "id": DUPLICATE_APPROVAL_FINDING_ID,
        "org_id": ORG_ID,
        "contract_id": DUPLICATE_APPROVAL_CONTRACT_ID,
        "version_id": DUPLICATE_APPROVAL_VERSION_ID,
        "title": "Liability cap is too low",
        "severity": "high",
        "description": "The liability cap is below a commercially reasonable threshold and leaves the customer exposed to outsized risk.",
        "recommendation": "Increase the cap to a more balanced level and align it with a market standard.",
        "evidence_quote": "The total liability cap for any claim is $100,000.",
        "evidence": {
            "text": "The total liability cap for any claim is $100,000.",
            "clause": "LIABILITY CAP",
        },
        "created_at": "2026-09-18T00:00:00Z",
    }


def _existing_duplicate_approval_proposal(proposals: FirestoreRepository) -> dict | None:
    for proposal in proposals.stream():
        if proposal.get("contract_id") == DUPLICATE_APPROVAL_CONTRACT_ID and proposal.get("finding_id") == DUPLICATE_APPROVAL_FINDING_ID:
            return proposal
    return None


def create_duplicate_approval_denial_fixture(
    orgs: OrganizationService,
    *,
    contracts: FirestoreRepository | None = None,
    versions: FirestoreRepository | None = None,
    findings: FirestoreRepository | None = None,
    service: ProposalService | None = None,
) -> dict[str, Any]:
    """Idempotently seed one contract/version/finding/proposal all the way to
    a real, persisted APPROVED state -- reached by actually calling
    ProposalService.create() then ProposalService.review() once, exactly the
    same code path a real reviewer's "Approve" click goes through. Safe to
    run any number of times: once APPROVED, this function only reads and
    validates, it never calls review() again."""
    contracts = contracts or FirestoreRepository("contracts")
    versions = versions or FirestoreRepository("contract_versions")
    findings = findings or FirestoreRepository("risk_findings")

    _ensure_org(orgs)
    if not contracts.get(DUPLICATE_APPROVAL_CONTRACT_ID):
        contracts.set(DUPLICATE_APPROVAL_CONTRACT_ID, _duplicate_approval_contract_record())
    if not versions.get(DUPLICATE_APPROVAL_VERSION_ID):
        versions.set(DUPLICATE_APPROVAL_VERSION_ID, _duplicate_approval_version_record())
    if not findings.get(DUPLICATE_APPROVAL_FINDING_ID):
        findings.set(DUPLICATE_APPROVAL_FINDING_ID, _duplicate_approval_finding_record())

    service = service or ProposalService(
        contracts=contracts, versions=versions, findings=findings, organizations=orgs,
    )
    existing = _existing_duplicate_approval_proposal(service.proposals)
    if existing:
        proposal = existing
    else:
        # Non-empty proposed_text -> create() auto-submits (draft -> in_review,
        # status PROPOSED), same as the original pending-review fixture.
        proposal = service.create(
            DUPLICATE_APPROVAL_CONTRACT_ID, DUPLICATE_APPROVAL_VERSION_ID, DUPLICATE_APPROVAL_FINDING_ID,
            DUPLICATE_APPROVAL_PROPOSED_TEXT, OWNER_ID,
        )

    current = service.get(proposal["proposal_id"], OWNER_ID)
    if current.get("status") == "PROPOSED":
        # Reach APPROVED through the real review() path exactly once.
        service.review(current["proposal_id"], "APPROVED", REVIEWER_ID, comment="Fixture: seeded APPROVED for duplicate-approval E2E test")
        current = service.get(current["proposal_id"], OWNER_ID)

    if current.get("status") != "APPROVED":
        raise RuntimeError(
            f"Expected duplicate-approval fixture proposal status APPROVED, got {current.get('status')!r}. "
            "This fixture never silently resets workflow state; if the proposal moved past APPROVED "
            f"(e.g. published), delete {DUPLICATE_APPROVAL_CONTRACT_ID}/{DUPLICATE_APPROVAL_FINDING_ID} "
            "manually and re-run."
        )
    decisions = [
        review for review in service.reviews.stream() if review.get("proposal_id") == current["proposal_id"]
    ]
    if len(decisions) != 1 or decisions[0].get("decision") != "APPROVED":
        raise RuntimeError(f"Expected exactly one APPROVED review record, got {decisions!r}")

    summary = {
        "org_id": ORG_ID,
        "contract_id": DUPLICATE_APPROVAL_CONTRACT_ID,
        "version_id": DUPLICATE_APPROVAL_VERSION_ID,
        "finding_id": DUPLICATE_APPROVAL_FINDING_ID,
        "proposal_id": current["proposal_id"],
        "proposal_status": current.get("status"),
        "workflow_instance_id": current.get("workflow_instance_id"),
        "contract_owner": OWNER_ID,
        "reviewer": REVIEWER_ID,
        "review_count": len(decisions),
    }
    print("[duplicate-approval] CONTRACT_ID:", summary["contract_id"])
    print("[duplicate-approval] FINDING_ID:", summary["finding_id"])
    print("[duplicate-approval] PROPOSAL_ID:", summary["proposal_id"])
    print("[duplicate-approval] PROPOSAL_STATUS:", summary["proposal_status"])
    print("[duplicate-approval] REVIEW_COUNT:", summary["review_count"])
    print("[duplicate-approval] READY_FOR_DUPLICATE_APPROVAL_ATTEMPT: yes")
    return summary


# ---------------------------------------------------------------------------
# Dual-role separation-of-duties fixture (E2E security/workflow follow-up,
# Phase 3): a SINGLE real identity holding BOTH contract_owner AND reviewer
# roles in the same org -- distinct from every other identity in this file,
# each of which deliberately holds exactly one role. This is what lets an
# E2E test prove the requires_not_actor rule specifically (workflow_catalog.py's
# "approve" transition), rather than the plain allowed_roles check: with a
# single-role owner (e.g. OWNER_ID above), WorkflowEngine._validate_transition
# rejects an approve attempt at the ROLE check before it ever reaches
# requires_not_actor (role check runs first -- see _validate_transition).
# Only an actor who legitimately HOLDS the reviewer role, and who is ALSO the
# instance's created_by, can actually exercise the SoD-specific guard.
#
# A dedicated new identity (not a role added to OWNER_ID) so this fixture
# never changes the role shape any other fixture or test in this file
# depends on.
DUAL_ROLE_SOD_ID = "demo-dual-role-1"
DUAL_ROLE_SOD_CONTRACT_ID = "demo-dual-role-sod-master-services-agreement"
DUAL_ROLE_SOD_VERSION_ID = "demo-dual-role-sod-master-services-agreement-v1"
DUAL_ROLE_SOD_FINDING_ID = "demo-dual-role-sod-liability-cap-finding"
DUAL_ROLE_SOD_CONTRACT_NAME = "Demo Dual-Role SoD Master Services Agreement"
DUAL_ROLE_SOD_PROPOSED_TEXT = (
    "The total liability cap for any claim shall be the greater of $650,000 or "
    "sixteen (16) months of fees paid in the preceding year."
)


def _dual_role_sod_contract_record() -> dict:
    return {
        "id": DUAL_ROLE_SOD_CONTRACT_ID,
        "org_id": ORG_ID,
        "owner_id": DUAL_ROLE_SOD_ID,
        "name": DUAL_ROLE_SOD_CONTRACT_NAME,
        "status": "uploaded",
        "current_version_id": DUAL_ROLE_SOD_VERSION_ID,
        "created_at": "2026-09-18T00:00:00Z",
        "updated_at": "2026-09-18T00:00:00Z",
    }


def _dual_role_sod_version_record() -> dict:
    return {
        "id": DUAL_ROLE_SOD_VERSION_ID,
        "org_id": ORG_ID,
        "contract_id": DUAL_ROLE_SOD_CONTRACT_ID,
        "owner_id": DUAL_ROLE_SOD_ID,
        "version_number": 1,
        "filename": "demo-dual-role-sod-master-services-agreement.txt",
        "content_type": "text/plain",
        "document_text": _document_text(),
        "analysis_status": "complete",
        "created_at": "2026-09-18T00:00:00Z",
    }


def _dual_role_sod_finding_record() -> dict:
    return {
        "id": DUAL_ROLE_SOD_FINDING_ID,
        "org_id": ORG_ID,
        "contract_id": DUAL_ROLE_SOD_CONTRACT_ID,
        "version_id": DUAL_ROLE_SOD_VERSION_ID,
        "title": "Liability cap is too low",
        "severity": "high",
        "description": "The liability cap is below a commercially reasonable threshold and leaves the customer exposed to outsized risk.",
        "recommendation": "Increase the cap to a more balanced level and align it with a market standard.",
        "evidence_quote": "The total liability cap for any claim is $100,000.",
        "evidence": {
            "text": "The total liability cap for any claim is $100,000.",
            "clause": "LIABILITY CAP",
        },
        "created_at": "2026-09-18T00:00:00Z",
    }


def _existing_dual_role_sod_proposal(proposals: FirestoreRepository) -> dict | None:
    for proposal in proposals.stream():
        if proposal.get("contract_id") == DUAL_ROLE_SOD_CONTRACT_ID and proposal.get("finding_id") == DUAL_ROLE_SOD_FINDING_ID:
            return proposal
    return None


def create_dual_role_sod_fixture(
    orgs: OrganizationService,
    *,
    contracts: FirestoreRepository | None = None,
    versions: FirestoreRepository | None = None,
    findings: FirestoreRepository | None = None,
    service: ProposalService | None = None,
) -> dict[str, Any]:
    """Idempotently seed DUAL_ROLE_SOD_ID (contract_owner + reviewer in the
    SAME org), a contract they own, and a proposal they create AND submit
    themselves (non-empty proposed_text -> auto-submit to PROPOSED, same as
    every other fixture in this file). Left at PROPOSED -- the E2E test (and
    a backend unit test) are what actually attempt the self-approval and
    assert it is denied by requires_not_actor. This function never calls
    review() itself, so it never risks racing or masking that assertion."""
    contracts = contracts or FirestoreRepository("contracts")
    versions = versions or FirestoreRepository("contract_versions")
    findings = findings or FirestoreRepository("risk_findings")

    _ensure_org(orgs)
    orgs.ensure_member(
        ORG_ID, DUAL_ROLE_SOD_ID, ["contract_owner", "reviewer"],
        email=f"{DUAL_ROLE_SOD_ID}@lexproof.local", invited_by=ADMIN_ID,
    )
    if not contracts.get(DUAL_ROLE_SOD_CONTRACT_ID):
        contracts.set(DUAL_ROLE_SOD_CONTRACT_ID, _dual_role_sod_contract_record())
    if not versions.get(DUAL_ROLE_SOD_VERSION_ID):
        versions.set(DUAL_ROLE_SOD_VERSION_ID, _dual_role_sod_version_record())
    if not findings.get(DUAL_ROLE_SOD_FINDING_ID):
        findings.set(DUAL_ROLE_SOD_FINDING_ID, _dual_role_sod_finding_record())

    service = service or ProposalService(
        contracts=contracts, versions=versions, findings=findings, organizations=orgs,
    )
    existing = _existing_dual_role_sod_proposal(service.proposals)
    if existing:
        proposal = existing
    else:
        proposal = service.create(
            DUAL_ROLE_SOD_CONTRACT_ID, DUAL_ROLE_SOD_VERSION_ID, DUAL_ROLE_SOD_FINDING_ID,
            DUAL_ROLE_SOD_PROPOSED_TEXT, DUAL_ROLE_SOD_ID,
        )

    current = service.get(proposal["proposal_id"], DUAL_ROLE_SOD_ID)
    if current.get("status") != "PROPOSED":
        raise RuntimeError(
            f"Expected dual-role-sod fixture proposal status PROPOSED, got {current.get('status')!r}. "
            "This fixture never resets workflow state; if something advanced it past PROPOSED, "
            f"delete {DUAL_ROLE_SOD_CONTRACT_ID}/{DUAL_ROLE_SOD_FINDING_ID} manually and re-run."
        )
    member = orgs.get_active_member(ORG_ID, DUAL_ROLE_SOD_ID)
    held_roles = list((member or {}).get("roles") or [])
    if "contract_owner" not in held_roles or "reviewer" not in held_roles:
        raise RuntimeError(f"Expected dual-role-sod identity to hold both contract_owner and reviewer, got {held_roles!r}")
    if current.get("created_by") != DUAL_ROLE_SOD_ID:
        raise RuntimeError(f"Expected proposal created_by={DUAL_ROLE_SOD_ID!r}, got {current.get('created_by')!r}")

    summary = {
        "org_id": ORG_ID,
        "contract_id": DUAL_ROLE_SOD_CONTRACT_ID,
        "version_id": DUAL_ROLE_SOD_VERSION_ID,
        "finding_id": DUAL_ROLE_SOD_FINDING_ID,
        "proposal_id": current["proposal_id"],
        "proposal_status": current.get("status"),
        "workflow_instance_id": current.get("workflow_instance_id"),
        "dual_role_user": DUAL_ROLE_SOD_ID,
        "dual_role_user_roles": held_roles,
    }
    print("[dual-role-sod] CONTRACT_ID:", summary["contract_id"])
    print("[dual-role-sod] FINDING_ID:", summary["finding_id"])
    print("[dual-role-sod] PROPOSAL_ID:", summary["proposal_id"])
    print("[dual-role-sod] PROPOSAL_STATUS:", summary["proposal_status"])
    print("[dual-role-sod] DUAL_ROLE_USER:", summary["dual_role_user"], "roles:", held_roles)
    print("[dual-role-sod] READY_FOR_SELF_APPROVAL_ATTEMPT: yes")
    return summary


# ---------------------------------------------------------------------------
# Cross-tenant isolation fixture (E2E security/workflow follow-up, Phase 2):
# a genuinely SEPARATE second organization ("Tenant B"), with its own real
# owner/reviewer identities and its own contract -- built entirely through
# the same real OrganizationService API every other org/member in this file
# goes through (create_org / ensure_member), never a hand-crafted parallel
# tenant model. Tenant A reuses the SAME existing identities and org
# (ORG_ID / OWNER_ID / REVIEWER_ID) already established above; this fixture
# only adds one NEW, dedicated Tenant-A contract (so this test never shares
# fixture state with golden-path/pending-review/duplicate-approval/
# dual-role-sod) plus the entire Tenant B org.
TENANT_B_ORG_ID = "lexproof-demo-tenant-b"
TENANT_B_ORG_NAME = "LexProof Demo Tenant B"
TENANT_B_OWNER_ID = "demo-tenant-b-owner-1"
TENANT_B_REVIEWER_ID = "demo-tenant-b-reviewer-1"

CROSS_TENANT_A_CONTRACT_ID = "demo-cross-tenant-a-master-services-agreement"
CROSS_TENANT_A_VERSION_ID = "demo-cross-tenant-a-master-services-agreement-v1"
CROSS_TENANT_A_FINDING_ID = "demo-cross-tenant-a-liability-cap-finding"
CROSS_TENANT_A_CONTRACT_NAME = "Demo Cross-Tenant A Master Services Agreement"
CROSS_TENANT_A_FINDING_TITLE = "Liability cap is too low"

CROSS_TENANT_B_CONTRACT_ID = "demo-cross-tenant-b-master-services-agreement"
CROSS_TENANT_B_VERSION_ID = "demo-cross-tenant-b-master-services-agreement-v1"
CROSS_TENANT_B_FINDING_ID = "demo-cross-tenant-b-liability-cap-finding"
CROSS_TENANT_B_CONTRACT_NAME = "Demo Cross-Tenant B Master Services Agreement"
CROSS_TENANT_B_FINDING_TITLE = "Payment terms are one-sided"


def _cross_tenant_contract_record(contract_id: str, org_id: str, owner_id: str, version_id: str, name: str) -> dict:
    return {
        "id": contract_id,
        "org_id": org_id,
        "owner_id": owner_id,
        "name": name,
        "status": "uploaded",
        "current_version_id": version_id,
        "created_at": "2026-09-18T00:00:00Z",
        "updated_at": "2026-09-18T00:00:00Z",
    }


def _cross_tenant_version_record(version_id: str, contract_id: str, org_id: str, owner_id: str, filename: str) -> dict:
    return {
        "id": version_id,
        "org_id": org_id,
        "contract_id": contract_id,
        "owner_id": owner_id,
        "version_number": 1,
        "filename": filename,
        "content_type": "text/plain",
        "document_text": _document_text(),
        "analysis_status": "complete",
        "created_at": "2026-09-18T00:00:00Z",
    }


def _cross_tenant_a_finding_record() -> dict:
    return {
        "id": CROSS_TENANT_A_FINDING_ID,
        "org_id": ORG_ID,
        "contract_id": CROSS_TENANT_A_CONTRACT_ID,
        "version_id": CROSS_TENANT_A_VERSION_ID,
        "title": CROSS_TENANT_A_FINDING_TITLE,
        "severity": "high",
        "description": "The liability cap is below a commercially reasonable threshold and leaves the customer exposed to outsized risk.",
        "recommendation": "Increase the cap to a more balanced level and align it with a market standard.",
        "evidence_quote": "The total liability cap for any claim is $100,000.",
        "evidence": {"text": "The total liability cap for any claim is $100,000.", "clause": "LIABILITY CAP"},
        "created_at": "2026-09-18T00:00:00Z",
    }


def _cross_tenant_b_finding_record() -> dict:
    return {
        "id": CROSS_TENANT_B_FINDING_ID,
        "org_id": TENANT_B_ORG_ID,
        "contract_id": CROSS_TENANT_B_CONTRACT_ID,
        "version_id": CROSS_TENANT_B_VERSION_ID,
        "title": CROSS_TENANT_B_FINDING_TITLE,
        "severity": "medium",
        "description": "Payment terms favor one party with no reciprocal late-payment protections.",
        "recommendation": "Align payment terms to a mutual, market-standard Net 30 with capped late interest.",
        "evidence_quote": "Customer will pay Fees within thirty (30) days after invoice.",
        "evidence": {"text": "Customer will pay Fees within thirty (30) days after invoice.", "clause": "PAYMENT"},
        "created_at": "2026-09-18T00:00:00Z",
    }


def create_cross_tenant_isolation_fixture(
    orgs: OrganizationService,
    *,
    contracts: FirestoreRepository | None = None,
    versions: FirestoreRepository | None = None,
    findings: FirestoreRepository | None = None,
) -> dict[str, Any]:
    """Idempotently seed a genuinely separate Tenant B org (own real
    owner/reviewer members, own contract) plus one dedicated new Tenant A
    contract, entirely through the real OrganizationService API. Never
    touches or reinterprets any other fixture's contract/org/identity."""
    contracts = contracts or FirestoreRepository("contracts")
    versions = versions or FirestoreRepository("contract_versions")
    findings = findings or FirestoreRepository("risk_findings")

    # Tenant A: reuse the existing org + owner/reviewer identities, add one
    # new dedicated contract.
    _ensure_org(orgs)
    if not contracts.get(CROSS_TENANT_A_CONTRACT_ID):
        contracts.set(
            CROSS_TENANT_A_CONTRACT_ID,
            _cross_tenant_contract_record(
                CROSS_TENANT_A_CONTRACT_ID, ORG_ID, OWNER_ID, CROSS_TENANT_A_VERSION_ID, CROSS_TENANT_A_CONTRACT_NAME,
            ),
        )
    if not versions.get(CROSS_TENANT_A_VERSION_ID):
        versions.set(
            CROSS_TENANT_A_VERSION_ID,
            _cross_tenant_version_record(
                CROSS_TENANT_A_VERSION_ID, CROSS_TENANT_A_CONTRACT_ID, ORG_ID, OWNER_ID,
                "demo-cross-tenant-a-master-services-agreement.txt",
            ),
        )
    if not findings.get(CROSS_TENANT_A_FINDING_ID):
        findings.set(CROSS_TENANT_A_FINDING_ID, _cross_tenant_a_finding_record())

    # Tenant B: a genuinely separate org, created (or reused) through the
    # real create_org API -- never a hand-crafted parallel model.
    if not orgs.orgs.get(TENANT_B_ORG_ID):
        orgs.create_org(
            TENANT_B_ORG_NAME,
            TENANT_B_OWNER_ID,
            org_id=TENANT_B_ORG_ID,
            creator_email=f"{TENANT_B_OWNER_ID}@lexproof.local",
            creator_display_name="Demo Tenant B Owner",
            roles=["contract_owner"],
        )
    orgs.ensure_member(
        TENANT_B_ORG_ID, TENANT_B_OWNER_ID, ["contract_owner"],
        email=f"{TENANT_B_OWNER_ID}@lexproof.local", invited_by=TENANT_B_OWNER_ID,
    )
    orgs.ensure_member(
        TENANT_B_ORG_ID, TENANT_B_REVIEWER_ID, ["reviewer"],
        email=f"{TENANT_B_REVIEWER_ID}@lexproof.local", invited_by=TENANT_B_OWNER_ID,
    )
    if not contracts.get(CROSS_TENANT_B_CONTRACT_ID):
        contracts.set(
            CROSS_TENANT_B_CONTRACT_ID,
            _cross_tenant_contract_record(
                CROSS_TENANT_B_CONTRACT_ID, TENANT_B_ORG_ID, TENANT_B_OWNER_ID, CROSS_TENANT_B_VERSION_ID, CROSS_TENANT_B_CONTRACT_NAME,
            ),
        )
    if not versions.get(CROSS_TENANT_B_VERSION_ID):
        versions.set(
            CROSS_TENANT_B_VERSION_ID,
            _cross_tenant_version_record(
                CROSS_TENANT_B_VERSION_ID, CROSS_TENANT_B_CONTRACT_ID, TENANT_B_ORG_ID, TENANT_B_OWNER_ID,
                "demo-cross-tenant-b-master-services-agreement.txt",
            ),
        )
    if not findings.get(CROSS_TENANT_B_FINDING_ID):
        findings.set(CROSS_TENANT_B_FINDING_ID, _cross_tenant_b_finding_record())

    # Validate: each user is an active member of exactly the org they should
    # be, and NOT an active member of the other tenant's org -- the fixture's
    # own proof that these are genuinely separate tenants, not just
    # differently-labeled contracts in the same org.
    checks = {
        (ORG_ID, OWNER_ID): True,
        (ORG_ID, REVIEWER_ID): True,
        (TENANT_B_ORG_ID, TENANT_B_OWNER_ID): True,
        (TENANT_B_ORG_ID, TENANT_B_REVIEWER_ID): True,
        (TENANT_B_ORG_ID, OWNER_ID): False,
        (TENANT_B_ORG_ID, REVIEWER_ID): False,
        (ORG_ID, TENANT_B_OWNER_ID): False,
        (ORG_ID, TENANT_B_REVIEWER_ID): False,
    }
    for (org_id, user_id), should_be_member in checks.items():
        is_member = bool(orgs.get_active_member(org_id, user_id))
        if is_member != should_be_member:
            raise RuntimeError(
                f"Cross-tenant fixture invariant violated: get_active_member({org_id!r}, {user_id!r}) "
                f"== {is_member!r}, expected {should_be_member!r}"
            )

    summary = {
        "tenant_a_org_id": ORG_ID,
        "tenant_a_owner": OWNER_ID,
        "tenant_a_reviewer": REVIEWER_ID,
        "tenant_a_contract_id": CROSS_TENANT_A_CONTRACT_ID,
        "tenant_b_org_id": TENANT_B_ORG_ID,
        "tenant_b_owner": TENANT_B_OWNER_ID,
        "tenant_b_reviewer": TENANT_B_REVIEWER_ID,
        "tenant_b_contract_id": CROSS_TENANT_B_CONTRACT_ID,
    }
    print("[cross-tenant] TENANT_A_ORG_ID:", summary["tenant_a_org_id"], "CONTRACT_ID:", summary["tenant_a_contract_id"])
    print("[cross-tenant] TENANT_B_ORG_ID:", summary["tenant_b_org_id"], "CONTRACT_ID:", summary["tenant_b_contract_id"])
    print("[cross-tenant] tenant_b_owner:", TENANT_B_OWNER_ID, "tenant_b_reviewer:", TENANT_B_REVIEWER_ID)
    print("[cross-tenant] READY_FOR_ISOLATION_TEST: yes")
    return summary



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        choices=["all", "pending-review", "golden-path", "duplicate-approval-denial", "dual-role-sod", "cross-tenant-isolation"],
        default="all",
        help="Which fixture(s) to provision. Default 'all' preserves this script's original behavior plus the new Phase 3J-B golden-path fixture.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete the selected fixture's proposal/workflow/reviews and re-seed it. "
            "Use with --fixture golden-path (fresh DRAFT) or --fixture pending-review "
            "(fresh PROPOSED). Does not apply to duplicate-approval-denial. Default "
            "--fixture all still only resets golden-path, matching prior behavior."
        ),
    )
    args = parser.parse_args()
    if args.reset and args.fixture == "duplicate-approval-denial":
        parser.error("--reset does not apply to the duplicate-approval-denial fixture")

    get_settings()
    orgs = OrganizationService(claims_refresher=lambda *args, **kwargs: None)
    if args.reset:
        service = ProposalService(organizations=orgs)
        if args.fixture == "pending-review":
            reset_pending_review_workflow_state(service)
        else:
            reset_golden_path_workflow_state(service)
    if args.fixture in ("all", "pending-review"):
        create_pending_review_fixture(orgs)
    if args.fixture in ("all", "golden-path"):
        create_golden_path_draft_fixture(orgs)
    if args.fixture in ("all", "duplicate-approval-denial"):
        create_duplicate_approval_denial_fixture(orgs)
    if args.fixture in ("all", "dual-role-sod"):
        create_dual_role_sod_fixture(orgs)
    if args.fixture in ("all", "cross-tenant-isolation"):
        create_cross_tenant_isolation_fixture(orgs)

    # Read-only diagnostic (no writes): reports the AUTHENTICATED_USER's
    # current org_memberships order, since frontend/components/OrgProvider.tsx
    # defaults X-Org-Id to orgs[0] on first login (no stored localStorage
    # preference yet) -- this tells us, from real data, whether the demo org
    # will be selected automatically or requires a manual org switch.
    authenticated_user_record = orgs.users.get(AUTHENTICATED_USER_ID) or {}
    memberships_order = list(authenticated_user_record.get("org_memberships") or [])
    print("[diagnostic] AUTHENTICATED_USER_ID:", AUTHENTICATED_USER_ID)
    print("[diagnostic] org_memberships (insertion order = /api/me orgs[] order):", memberships_order)
    if memberships_order:
        print(
            "[diagnostic] default X-Org-Id after login (orgs[0], absent a stored "
            f"preference): {memberships_order[0]!r}"
            + (" -- MATCHES lexproof-demo" if memberships_order[0] == ORG_ID else " -- does NOT match lexproof-demo; a manual org switch (or a stored localStorage preference) would be needed")
        )


if __name__ == "__main__":
    main()
