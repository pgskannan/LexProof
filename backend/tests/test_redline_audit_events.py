"""Phase 3E: audit trail integrity for the Reviewer -> Approver workflow.

Phase 1/2 audit finding (P1): approve/reject decisions were fully recorded in
the per-workflow-instance history (services/workflow_engine.py's append-only
history subcollection, including actor_roles_at_time), but NOT represented in
the cross-cutting, org-scoped audit_log that GET /audit-log reads -- the view
meant to let an org Admin/Auditor reconstruct "everything that happened in
this org" without knowing which workflow instance to look at.

This file proves, through the real FastAPI endpoints (not by calling the
service layer directly, since record_audit_event() is only invoked from the
api/redline_proposals.py router, not from ProposalService itself):

  - Creating a redline proposal now writes a "redline.created" event (this
    event genuinely did not exist before Phase 3E -- the only true gap;
    "redline.approved"/"redline.rejected"/"redline.published" were already
    wired up in the committed baseline (commit 373d7b8), just untested and,
    for the review events, missing their comment/workflow-instance/actor-role
    detail in metadata).
  - Approval and rejection each write exactly one, correctly-shaped
    cross-cutting audit_log event, in addition to (not instead of) the
    existing workflow-instance history event.
  - The existing "redline.published" event still carries contract_id
    (regression guard for the previously-fixed publish audit bug).
  - Audit events carry the correct org_id (tenant isolation) and are never
    written when the workflow-level authorization check itself rejects the
    caller.
  - No call produces duplicate audit_log entries.

record_audit_event()'s default `repository_factory` parameter is bound to the
real FirestoreRepository at import time (see services/audit.py) -- patching
`contracts_api.FirestoreRepository`-style aliases elsewhere has no effect on
it, because Python binds default argument values once, at function-definition
time, not by name lookup on every call. So rather than reimplementing
record_audit_event's behavior as a mock, this file replaces
`proposal_api.record_audit_event` itself with a thin wrapper that calls the
real function with `repository_factory=FakeRepository` explicitly injected --
every real code path in services/audit.py still runs, only the storage
backend changes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lexproof.api import redline_proposals as proposal_api
from app.lexproof.main import create_app
from app.lexproof.services.audit import record_audit_event as real_record_audit_event
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.redline_proposals import ProposalService
from app.lexproof.services.workflow_engine import WorkflowEngine
from tests.fakes import FakeRepository

ORG_A = "org-a"
ORG_B = "org-b"


def seed_data():
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": ORG_A, "current_version_id": "version-1"},
        },
        "contract_versions": {
            "version-1": {
                "id": "version-1", "contract_id": "contract-1", "owner_id": "owner-1", "version_number": 1,
                "content_hash": "hash-v1", "document_text": "Before clause. Exact clause text. After clause.",
            },
        },
        "risk_findings": {
            "finding-1": {
                "id": "finding-1", "contract_id": "contract-1", "version_id": "version-1", "title": "Liability cap",
                "severity": "critical", "description": "The cap is too low.", "evidence": "Clause text",
                "evidence_quote": "Exact clause text", "recommendation": "Review the cap.",
                "created_at": datetime.now(timezone.utc),
            },
        },
        "redline_proposals": {},
        "redline_reviews": {},
        "redline_publication_audits": {},
        "organizations": {
            ORG_A: {"org_id": ORG_A, "name": "Org A", "status": "active"},
            ORG_B: {"org_id": ORG_B, "name": "Org B", "status": "active"},
        },
        f"organizations/{ORG_A}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_A},
            "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_A},
            "approver-1": {"user_id": "approver-1", "roles": ["approver"], "status": "active", "org_id": ORG_A},
            "auditor-1": {"user_id": "auditor-1", "roles": ["auditor"], "status": "active", "org_id": ORG_A},
        },
        f"organizations/{ORG_B}/members": {
            "foreign-reviewer-1": {"user_id": "foreign-reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_B},
        },
        "users": {},
        "organization_invites": {},
        "workflow_definitions": {},
        "workflow_instances": {},
        "audit_log": {},
    }


def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def make_workflow() -> WorkflowEngine:
    return WorkflowEngine(
        definitions=FakeRepository("workflow_definitions"),
        instances=FakeRepository("workflow_instances"),
        history_factory=lambda instance_id: FakeRepository(f"workflow_instances/{instance_id}/history"),
    )


def make_service() -> ProposalService:
    return ProposalService(
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        reviews=FakeRepository("redline_reviews"),
        publication_audits=FakeRepository("redline_publication_audits"),
        passports=FakeRepository("legal_passports"),
        evidence_records=FakeRepository("evidence_records"),
        evidence_anchors=FakeRepository("evidence_anchors"),
        analysis_service=None,
        organizations=make_orgs(),
        workflow=make_workflow(),
    )


def make_client(monkeypatch, uid: str) -> TestClient:
    seed_data()
    service = make_service()
    monkeypatch.setattr(proposal_api, "_service", lambda: service)

    def fake_record_audit_event(**kwargs):
        # Forwards to the real, unmodified record_audit_event body -- only
        # the storage backend is swapped for the in-memory fake. See module
        # docstring for why this is necessary (default-arg binding).
        return real_record_audit_event(FakeRepository, **kwargs)

    monkeypatch.setattr(proposal_api, "record_audit_event", fake_record_audit_event)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def audit_events(action: str | None = None) -> list[dict]:
    events = list(FakeRepository("audit_log").stream())
    if action is not None:
        events = [event for event in events if event.get("action") == action]
    return events


def create_proposal(client: TestClient) -> str:
    created = client.post(
        "/api/contracts/contract-1/redline-proposals",
        json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Revised clause"},
    )
    assert created.status_code == 201
    return created.json()["proposal_id"]


# ---------------------------------------------------------------------------
# 1. Proposal creation
# ---------------------------------------------------------------------------

def test_creating_a_proposal_writes_a_created_audit_event(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)

    events = audit_events("redline.created")
    assert len(events) == 1
    event = events[0]
    assert event["resource_id"] == proposal_id
    assert event["resource_type"] == "redline_proposal"
    assert event["contract_id"] == "contract-1"
    assert event["org_id"] == ORG_A
    assert event["actor_id"] == "owner-1"


# ---------------------------------------------------------------------------
# 2. Approval
# ---------------------------------------------------------------------------

def test_approval_updates_workflow_state_and_writes_audit_event(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)

    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    reviewed = client.post(
        f"/api/redline-proposals/{proposal_id}/review",
        json={"decision": "APPROVED", "comment": "Looks good"},
    )
    assert reviewed.status_code == 200

    # Workflow state changed.
    proposal_record = FakeRepository.stores["redline_proposals"][proposal_id]
    assert proposal_record["status"] == "APPROVED"
    instance_id = proposal_record["workflow_instance_id"]
    assert instance_id

    # Workflow-instance history still records the transition (this file must
    # not weaken or replace that surface).
    service = make_service()  # fresh instance is fine -- workflow storage is the shared FakeRepository class store
    history = service.workflow.get_instance_history(instance_id)
    approve_events = [event for event in history if event["transition_id"] == "approve"]
    assert len(approve_events) == 1
    assert approve_events[0]["actor_id"] == "reviewer-1"
    assert approve_events[0]["actor_roles_at_time"] == ["reviewer"]
    assert approve_events[0]["comment"] == "Looks good"

    # Cross-cutting audit_log now also has exactly one matching event.
    events = audit_events("redline.approved")
    assert len(events) == 1
    event = events[0]
    assert event["resource_id"] == proposal_id
    assert event["resource_type"] == "redline_proposal"
    assert event["contract_id"] == "contract-1"
    assert event["org_id"] == ORG_A
    assert event["actor_id"] == "reviewer-1"
    assert event["metadata"]["comment"] == "Looks good"
    assert event["metadata"]["workflow_instance_id"] == instance_id
    assert event["metadata"]["actor_roles"] == ["reviewer"]


def test_single_approval_creates_exactly_one_audit_event(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}

    response = client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"})
    assert response.status_code == 200

    assert len(audit_events("redline.approved")) == 1
    # A second attempt is rejected by the existing final-decision guard and
    # must not add another approval event.
    again = client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"})
    assert again.status_code == 409
    assert len(audit_events("redline.approved")) == 1


# ---------------------------------------------------------------------------
# 3. Rejection
# ---------------------------------------------------------------------------

def test_rejection_updates_workflow_state_and_writes_audit_event(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)

    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    reviewed = client.post(
        f"/api/redline-proposals/{proposal_id}/review",
        json={"decision": "REJECTED", "comment": "Needs negotiation"},
    )
    assert reviewed.status_code == 200

    proposal_record = FakeRepository.stores["redline_proposals"][proposal_id]
    assert proposal_record["status"] == "REJECTED"
    instance_id = proposal_record["workflow_instance_id"]

    service = make_service()
    history = service.workflow.get_instance_history(instance_id)
    reject_events = [event for event in history if event["transition_id"] == "reject"]
    assert len(reject_events) == 1
    assert reject_events[0]["comment"] == "Needs negotiation"

    events = audit_events("redline.rejected")
    assert len(events) == 1
    event = events[0]
    assert event["resource_id"] == proposal_id
    assert event["contract_id"] == "contract-1"
    assert event["org_id"] == ORG_A
    assert event["actor_id"] == "reviewer-1"
    assert event["metadata"]["comment"] == "Needs negotiation"


def test_single_rejection_creates_exactly_one_audit_event(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}

    response = client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "REJECTED"})
    assert response.status_code == 200

    assert len(audit_events("redline.rejected")) == 1
    assert len(audit_events("redline.approved")) == 0


# ---------------------------------------------------------------------------
# 4. Publish regression (previously-fixed contract_id bug must stay fixed)
# ---------------------------------------------------------------------------

def test_publish_audit_event_still_carries_contract_id(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 200

    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "approver-1"}
    published = client.post(f"/api/redline-proposals/{proposal_id}/publish")
    assert published.status_code == 200

    events = audit_events("redline.published")
    assert len(events) == 1
    event = events[0]
    assert event["contract_id"] == "contract-1"
    assert event["resource_id"] == proposal_id
    assert event["org_id"] == ORG_A


# ---------------------------------------------------------------------------
# 5. Tenant isolation
# ---------------------------------------------------------------------------

def test_approval_audit_event_carries_the_reviewers_own_org(monkeypatch):
    """The event's org_id must be the proposal's real organization -- an
    org-scoped audit view (GET /audit-log) relies on this field alone to
    keep one org's decisions from appearing in another's feed."""
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 200

    events = audit_events("redline.approved")
    assert len(events) == 1
    assert events[0]["org_id"] == ORG_A
    assert events[0]["org_id"] != ORG_B


# ---------------------------------------------------------------------------
# 6. Authorization: a rejected transition must not leave an audit trace
# ---------------------------------------------------------------------------

def test_unauthorized_actor_cannot_generate_an_audit_event(monkeypatch):
    """A member of a different org (no standing over this proposal at all)
    must be rejected by the workflow/org membership check before
    record_audit_event is ever reached."""
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)

    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "foreign-reviewer-1"}
    response = client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"})
    assert response.status_code == 403

    assert audit_events("redline.approved") == []
    assert audit_events("redline.rejected") == []


def test_creator_cannot_self_approve_and_generates_no_audit_event(monkeypatch):
    """Separation-of-duties (unchanged by this phase): the proposal's own
    creator cannot approve it, and the blocked attempt must not create a
    stray approval audit event either."""
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)

    response = client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"})
    assert response.status_code == 403

    assert audit_events("redline.approved") == []


def test_auditor_role_cannot_approve_and_generates_no_audit_event(monkeypatch):
    """A read-only Auditor role must not be able to transition the workflow,
    and must not be able to generate an approval audit event by attempting to."""
    client = make_client(monkeypatch, "owner-1")
    proposal_id = create_proposal(client)

    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "auditor-1"}
    response = client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"})
    assert response.status_code == 403

    assert audit_events("redline.approved") == []
