"""Idempotent migration: default org, org_id backfill, admin member, workflow history.

Usage (from the backend/ directory):
    .\\.venv\\Scripts\\python.exe scripts\\migrate_org_workflow.py --email you@example.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lexproof.config import get_settings
from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.services.organizations import DEFAULT_ORG_ID, DEFAULT_ORG_NAME, OrganizationService
from app.lexproof.services.workflow_catalog import (
    CONTRACT_REDLINE_APPROVAL,
    CONTRACT_REDLINE_STATES,
    CONTRACT_REDLINE_TRANSITIONS,
    STATE_BY_PROPOSAL_STATUS,
    redline_definition_id,
)
from app.lexproof.services.workflow_engine import INSTANCE_COMPLETED, INSTANCE_IN_PROGRESS, WorkflowEngine

COLLECTIONS_WITH_ORG = (
    "contracts",
    "contract_versions",
    "legal_passports",
    "redline_proposals",
    "redline_reviews",
    "risk_findings",
    "evidence_records",
)


def _resolve_user(email: str) -> tuple[str, str | None, str | None]:
    from app.lexproof.services.firebase import initialize_firebase
    from firebase_admin import auth

    initialize_firebase()
    record = auth.get_user_by_email(email)
    return record.uid, record.email, record.display_name


def _stamp_org_id(name: str, org_id: str) -> int:
    repo = FirestoreRepository(name)
    updated = 0
    for record in repo.stream():
        document_id = record.get("id")
        if not document_id:
            continue
        if record.get("org_id") == org_id:
            continue
        if record.get("org_id"):
            continue
        repo.set(document_id, {"org_id": org_id}, merge=True)
        updated += 1
    return updated


def _backfill_workflows(org_id: str, engine: WorkflowEngine) -> int:
    proposals = FirestoreRepository("redline_proposals")
    reviews = list(FirestoreRepository("redline_reviews").stream())
    reviews_by_proposal = {}
    for review in reviews:
        proposal_id = review.get("proposal_id")
        if proposal_id and proposal_id not in reviews_by_proposal:
            reviews_by_proposal[proposal_id] = review
    definition = engine.create_definition(
        org_id,
        CONTRACT_REDLINE_APPROVAL,
        CONTRACT_REDLINE_STATES,
        CONTRACT_REDLINE_TRANSITIONS,
        "migration",
        definition_id=redline_definition_id(org_id),
    )
    created = 0
    for proposal in proposals.stream():
        proposal_id = proposal.get("proposal_id") or proposal.get("id")
        if not proposal_id:
            continue
        review = reviews_by_proposal.get(proposal_id)
        instance = engine.find_instance(org_id, "redline_proposal", proposal_id)
        if instance is None:
            instance = engine.start_instance(
                org_id,
                definition["definition_id"],
                "redline_proposal",
                proposal_id,
                proposal.get("created_by") or "migration",
                metadata={"contract_id": proposal.get("contract_id")},
            )
            created += 1
        history = engine.get_instance_history(instance["instance_id"])
        target_state = STATE_BY_PROPOSAL_STATUS.get(str(proposal.get("status") or "").upper(), instance["current_state"])
        terminal = target_state in {"published", "rejected"}
        engine.instances.set(
            instance["instance_id"],
            {
                "current_state": target_state,
                "status": INSTANCE_COMPLETED if terminal else INSTANCE_IN_PROGRESS,
                "org_id": org_id,
            },
            merge=True,
        )
        if review and not history:
            event_id = review.get("review_id") or f"migrated-{proposal_id}"
            decision = str(review.get("decision") or "").upper()
            engine.history(instance["instance_id"]).set(
                event_id,
                {
                    "event_id": event_id,
                    "instance_id": instance["instance_id"],
                    "transition_id": "approve" if decision == "APPROVED" else "reject",
                    "from_state": "in_review",
                    "to_state": "approved" if decision == "APPROVED" else "rejected",
                    "actor_id": review.get("reviewer_id"),
                    "actor_roles_at_time": ["reviewer"],
                    "comment": review.get("comment"),
                    "occurred_at": review.get("created_at"),
                    "migrated": True,
                },
            )
        if proposal.get("workflow_instance_id") != instance["instance_id"] or proposal.get("org_id") != org_id:
            proposals.set(
                proposal_id,
                {"workflow_instance_id": instance["instance_id"], "org_id": org_id},
                merge=True,
            )
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill LexProof Demo org, membership, and workflow history.")
    parser.add_argument("--email", required=True, help="Firebase user email to make Admin of the default org")
    args = parser.parse_args()

    get_settings()
    uid, email, display_name = _resolve_user(args.email.strip())
    orgs = OrganizationService(claims_refresher=lambda *a, **k: None)
    org = orgs.create_org(DEFAULT_ORG_NAME, uid, org_id=DEFAULT_ORG_ID, creator_email=email, creator_display_name=display_name)
    orgs.ensure_member(DEFAULT_ORG_ID, uid, ["admin"], email=email, invited_by=uid)
    print(f"Organization {org['org_id']} ({org.get('name')}) ready. Admin member: {uid} <{email}>")

    for collection in COLLECTIONS_WITH_ORG:
        updated = _stamp_org_id(collection, DEFAULT_ORG_ID)
        print(f"Stamped org_id on {updated} {collection} document(s)")

    contracts = FirestoreRepository("contracts")
    for contract in contracts.stream():
        owner_id = contract.get("owner_id")
        if owner_id:
            orgs.ensure_member(DEFAULT_ORG_ID, owner_id, ["contract_owner"], invited_by=uid)

    engine = WorkflowEngine()
    created = _backfill_workflows(DEFAULT_ORG_ID, engine)
    print(f"Workflow instances created or reused for reviewed proposals: {created}")
    print("Migration complete (idempotent; safe to re-run).")


if __name__ == "__main__":
    main()
