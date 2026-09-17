"""Unit tests for the workflow engine's SLA due-date and escalation
support: due-date computation on state entry, overdue detection, the
overdue-instance sweep, escalation notification hand-off, and idempotency."""

from datetime import datetime, timedelta, timezone

from app.lexproof.services.workflow_engine import (
    WorkflowEngine,
    is_overdue,
)
from tests.fakes import FakeRepository

ORG_ID = "org-sla-1"

STATES = [
    {
        "id": "draft",
        "name": "Draft",
        "is_initial": True,
        "is_terminal": False,
        "sla_hours": 1,
        "escalate_to_roles": ["lead"],
    },
    {"id": "approved", "name": "Approved", "is_initial": False, "is_terminal": True},
    {"id": "rejected", "name": "Rejected", "is_initial": False, "is_terminal": True, "sla_hours": 2},
]
TRANSITIONS = [
    {
        "id": "approve",
        "from_state": "draft",
        "to_state": "approved",
        "action_name": "Approve",
        "allowed_roles": ["approver"],
        "requires_not_actor": [],
    },
    {
        "id": "reject",
        "from_state": "draft",
        "to_state": "rejected",
        "action_name": "Reject",
        "allowed_roles": ["approver"],
        "requires_not_actor": [],
    },
]


def engine() -> WorkflowEngine:
    FakeRepository.stores = {}
    return WorkflowEngine(
        definitions=FakeRepository("workflow_definitions"),
        instances=FakeRepository("workflow_instances"),
        history_factory=lambda instance_id: FakeRepository(f"workflow_instances/{instance_id}/history"),
    )


def started_instance(service: WorkflowEngine | None = None, created_by: str = "owner-1"):
    service = service or engine()
    definition = service.create_definition(ORG_ID, "sla-demo", STATES, TRANSITIONS, "admin-1")
    instance = service.start_instance(ORG_ID, definition["definition_id"], "document", "doc-1", created_by)
    return service, definition, instance


def test_start_instance_computes_sla_due_at_from_initial_state_hours():
    service, _definition, instance = started_instance()
    assert instance["sla_due_at"] is not None
    entered = datetime.fromisoformat(instance["state_entered_at"])
    due = datetime.fromisoformat(instance["sla_due_at"])
    assert due - entered == timedelta(hours=1)
    assert instance["escalated_at"] is None
    # Freshly created and due an hour from now -- not overdue yet.
    assert is_overdue(instance) is False


def test_state_without_sla_hours_has_no_due_date():
    service, definition, instance = started_instance()
    updated = service.execute_transition(instance["instance_id"], "approve", "approver-1", ["approver"])
    assert updated["current_state"] == "approved"
    assert updated["sla_due_at"] is None
    assert is_overdue(updated) is False


def test_transition_recomputes_due_date_and_clears_prior_escalation():
    service, definition, instance = started_instance()
    # Simulate a previous escalation on the draft state before it transitions.
    service.instances.set(instance["instance_id"], {"escalated_at": "2020-01-01T00:00:00+00:00"}, merge=True)
    updated = service.execute_transition(instance["instance_id"], "reject", "approver-1", ["approver"])
    assert updated["current_state"] == "rejected"
    assert updated["escalated_at"] is None
    entered = datetime.fromisoformat(updated["state_entered_at"])
    due = datetime.fromisoformat(updated["sla_due_at"])
    assert due - entered == timedelta(hours=2)


def test_is_overdue_false_when_not_in_progress_even_if_due_date_passed():
    instance = {
        "status": "completed",
        "sla_due_at": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
    }
    assert is_overdue(instance) is False


def test_is_overdue_true_when_in_progress_past_due_date():
    instance = {
        "status": "in_progress",
        "sla_due_at": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
    }
    assert is_overdue(instance) is True


def _backdate(service: WorkflowEngine, instance_id: str, hours_ago: float) -> None:
    due = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    service.instances.set(instance_id, {"sla_due_at": due}, merge=True)


def test_list_overdue_instances_returns_only_the_overdue_ones():
    service = engine()
    definition = service.create_definition(ORG_ID, "sla-demo", STATES, TRANSITIONS, "admin-1")
    overdue = service.start_instance(ORG_ID, definition["definition_id"], "document", "doc-overdue", "owner-1")
    fresh = service.start_instance(ORG_ID, definition["definition_id"], "document", "doc-fresh", "owner-1")
    _backdate(service, overdue["instance_id"], hours_ago=3)

    results = service.list_overdue_instances(ORG_ID)

    result_ids = {item["instance_id"] for item in results}
    assert overdue["instance_id"] in result_ids
    assert fresh["instance_id"] not in result_ids


def test_escalate_overdue_notifies_once_and_is_idempotent():
    service = engine()
    definition = service.create_definition(ORG_ID, "sla-demo", STATES, TRANSITIONS, "admin-1")
    instance = service.start_instance(ORG_ID, definition["definition_id"], "document", "doc-1", "owner-1")
    _backdate(service, instance["instance_id"], hours_ago=3)

    calls = []

    def notify(inst, defn, roles):
        calls.append((inst["instance_id"], roles))

    first = service.escalate_overdue(ORG_ID, notify=notify)
    assert len(first) == 1
    assert first[0]["escalated_at"] is not None
    assert calls == [(instance["instance_id"], ["lead"])]

    second = service.escalate_overdue(ORG_ID, notify=notify)
    assert second == []
    assert calls == [(instance["instance_id"], ["lead"])]


def test_escalate_overdue_marks_escalated_even_without_roles_but_skips_notify():
    service = engine()
    no_escalate_states = [
        {"id": "draft", "name": "Draft", "is_initial": True, "is_terminal": False, "sla_hours": 1},
        {"id": "approved", "name": "Approved", "is_initial": False, "is_terminal": True},
    ]
    transitions = [
        {
            "id": "approve",
            "from_state": "draft",
            "to_state": "approved",
            "action_name": "Approve",
            "allowed_roles": ["approver"],
            "requires_not_actor": [],
        }
    ]
    definition = service.create_definition(ORG_ID, "no-escalate", no_escalate_states, transitions, "admin-1")
    instance = service.start_instance(ORG_ID, definition["definition_id"], "document", "doc-2", "owner-1")
    _backdate(service, instance["instance_id"], hours_ago=3)

    calls = []
    result = service.escalate_overdue(ORG_ID, notify=lambda inst, defn, roles: calls.append(roles))

    assert len(result) == 1
    assert result[0]["escalated_at"] is not None
    assert calls == []


def test_update_definition_content_replaces_states_in_place():
    service, definition, _instance = started_instance()
    new_states = [{**state, "sla_hours": 99} if state["id"] == "draft" else state for state in STATES]
    updated = service.update_definition_content(definition["definition_id"], new_states, TRANSITIONS)

    assert updated["definition_id"] == definition["definition_id"]
    assert updated["version"] == definition["version"]
    assert updated["states"][0]["sla_hours"] == 99

    refetched = service.get_definition(definition["definition_id"])
    assert refetched["states"][0]["sla_hours"] == 99
