"""Tests for the bridge between the generic workflow-engine escalation sweep
and concrete in-app notifications: only active members holding one of the
escalated-to roles get notified, and the sweep is safe to call repeatedly."""

from datetime import datetime, timedelta, timezone

from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.workflow_engine import WorkflowEngine
from app.lexproof.services.workflow_escalation import WorkflowEscalationService
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"

STATES = [
    {
        "id": "in_review",
        "name": "In review",
        "is_initial": True,
        "is_terminal": False,
        "sla_hours": 1,
        "escalate_to_roles": ["admin"],
    },
    {"id": "approved", "name": "Approved", "is_initial": False, "is_terminal": True},
]
TRANSITIONS = [
    {
        "id": "approve",
        "from_state": "in_review",
        "to_state": "approved",
        "action_name": "Approve",
        "allowed_roles": ["admin"],
        "requires_not_actor": [],
    }
]


def seed_org_members():
    FakeRepository.stores = {
        "organizations": {ORG_ID: {"org_id": ORG_ID, "name": "LexProof Demo", "status": "active"}},
        f"organizations/{ORG_ID}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_ID},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": ORG_ID},
            "admin-2-deactivated": {
                "user_id": "admin-2-deactivated", "roles": ["admin"], "status": "deactivated", "org_id": ORG_ID,
            },
        },
        "users": {},
        "organization_invites": {},
        "workflow_definitions": {},
        "workflow_instances": {},
        "notifications": {},
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


def notifications():
    return list(FakeRepository("notifications").stream())


def test_sweep_notifies_only_active_members_with_an_escalated_role():
    seed_org_members()
    workflow = make_workflow()
    definition = workflow.create_definition(ORG_ID, "review", STATES, TRANSITIONS, "admin-1")
    instance = workflow.start_instance(ORG_ID, definition["definition_id"], "redline_proposal", "proposal-1", "owner-1")
    workflow.instances.set(
        instance["instance_id"],
        {"sla_due_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()},
        merge=True,
    )
    service = WorkflowEscalationService(workflow=workflow, organizations=make_orgs(), repository_factory=FakeRepository)

    escalated = service.sweep_org(ORG_ID)

    assert len(escalated) == 1
    notes = notifications()
    owner_ids = {note["owner_id"] for note in notes}
    assert owner_ids == {"admin-1"}
    assert notes[0]["type"] == "workflow_overdue"
    assert notes[0]["read"] is False


def test_sweep_is_a_no_op_second_time_for_the_same_instance():
    seed_org_members()
    workflow = make_workflow()
    definition = workflow.create_definition(ORG_ID, "review", STATES, TRANSITIONS, "admin-1")
    instance = workflow.start_instance(ORG_ID, definition["definition_id"], "redline_proposal", "proposal-1", "owner-1")
    workflow.instances.set(
        instance["instance_id"],
        {"sla_due_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()},
        merge=True,
    )
    service = WorkflowEscalationService(workflow=workflow, organizations=make_orgs(), repository_factory=FakeRepository)

    service.sweep_org(ORG_ID)
    assert len(notifications()) == 1

    second = service.sweep_org(ORG_ID)
    assert second == []
    assert len(notifications()) == 1


def test_sweep_finds_nothing_when_no_instance_is_overdue():
    seed_org_members()
    workflow = make_workflow()
    definition = workflow.create_definition(ORG_ID, "review", STATES, TRANSITIONS, "admin-1")
    workflow.start_instance(ORG_ID, definition["definition_id"], "redline_proposal", "proposal-1", "owner-1")
    service = WorkflowEscalationService(workflow=workflow, organizations=make_orgs(), repository_factory=FakeRepository)

    assert service.sweep_org(ORG_ID) == []
    assert notifications() == []


def test_sweep_also_posts_a_chat_notification_for_each_escalated_instance():
    seed_org_members()
    workflow = make_workflow()
    definition = workflow.create_definition(ORG_ID, "review", STATES, TRANSITIONS, "admin-1")
    instance = workflow.start_instance(ORG_ID, definition["definition_id"], "redline_proposal", "proposal-1", "owner-1")
    workflow.instances.set(
        instance["instance_id"],
        {"sla_due_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()},
        merge=True,
    )
    calls: list[dict] = []

    class RecordingChat:
        def notify_org(self, org_id, *, event_type, title, message, url=None):
            calls.append({"org_id": org_id, "event_type": event_type, "title": title, "message": message, "url": url})
            return []

    service = WorkflowEscalationService(
        workflow=workflow, organizations=make_orgs(), chat=RecordingChat(), repository_factory=FakeRepository,
    )

    service.sweep_org(ORG_ID)

    assert len(calls) == 1
    assert calls[0]["org_id"] == ORG_ID
    assert calls[0]["event_type"] == "workflow_overdue"
    assert "In review" in calls[0]["title"]


def test_sweep_survives_a_chat_notification_failure():
    seed_org_members()
    workflow = make_workflow()
    definition = workflow.create_definition(ORG_ID, "review", STATES, TRANSITIONS, "admin-1")
    instance = workflow.start_instance(ORG_ID, definition["definition_id"], "redline_proposal", "proposal-1", "owner-1")
    workflow.instances.set(
        instance["instance_id"],
        {"sla_due_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()},
        merge=True,
    )

    class RaisingChat:
        def notify_org(self, *args, **kwargs):
            raise RuntimeError("boom")

    service = WorkflowEscalationService(
        workflow=workflow, organizations=make_orgs(), chat=RaisingChat(), repository_factory=FakeRepository,
    )

    # The in-app notification still gets written even though chat delivery blew up.
    escalated = service.sweep_org(ORG_ID)
    assert len(escalated) == 1
    assert len(notifications()) == 1
