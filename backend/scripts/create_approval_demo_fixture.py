"""Create one deterministic pre-approval redline workflow fixture.

This script creates a single demo scenario through the real LexProof workflow:
the contract owner creates a redline proposal from a persisted finding, the
proposal enters human review, and an approver is available for the later
publication transition. No review decision is recorded by this fixture.

Usage:
    python scripts/create_approval_demo_fixture.py
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def _existing_proposal() -> dict | None:
    proposals = FirestoreRepository("redline_proposals")
    for proposal in proposals.stream():
        if proposal.get("contract_id") == CONTRACT_ID and proposal.get("finding_id") == FINDING_ID:
            return proposal
    return None


def main() -> None:
    get_settings()
    orgs = OrganizationService(claims_refresher=lambda *args, **kwargs: None)
    _ensure_org(orgs)
    _ensure_contract_and_version()
    _ensure_finding()

    service = ProposalService(organizations=orgs)
    existing = _existing_proposal()
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
        raise RuntimeError(f"Expected proposal status PROPOSED, got {final.get('status')!r}")
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
    print("ORG_ID:", ORG_ID)
    print("CONTRACT_ID:", CONTRACT_ID)
    print("VERSION_ID:", VERSION_ID)
    print("FINDING_ID:", FINDING_ID)
    print("PROPOSAL:", proposal_state)
    print("WORKFLOW:", workflow_state)
    print("REVIEW_DECISION: pending")
    print("APPROVAL_INSTANCE:", instance.get("instance_id"))
    print("APPROVER:", approver_state)
    print("AUTHENTICATED_USER:", authenticated_user_state)
    print("PUBLISHED_VERSION_ID:", final.get("published_version_id"))
    print("APPROVAL_STATE:", approval_state)
    print("READY_FOR_MANUAL_REVIEW: yes")


if __name__ == "__main__":
    main()
