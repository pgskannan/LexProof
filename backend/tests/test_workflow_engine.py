"""Unit tests for the generic workflow engine using an in-memory Firestore fake."""

from app.lexproof.services.workflow_engine import (
    WorkflowPermissionError,
    WorkflowSeparationOfDutiesError,
    WorkflowTransitionError,
    WorkflowEngine,
)
from tests.fakes import FakeRepository

ORG_ID = "org-1"

STATES = [
    {"id": "draft", "name": "Draft", "is_initial": True, "is_terminal": False},
    {"id": "approved", "name": "Approved", "is_initial": False, "is_terminal": True},
    {"id": "rejected", "name": "Rejected", "is_initial": False, "is_terminal": True},
]
TRANSITIONS = [
    {
        "id": "approve",
        "from_state": "draft",
        "to_state": "approved",
        "action_name": "Approve",
        "allowed_roles": ["approver", "admin"],
        "requires_not_actor": ["created_by"],
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


def started_instance(created_by: str = "owner-1"):
    service = engine()
    definition = service.create_definition(ORG_ID, "generic", STATES, TRANSITIONS, "admin-1")
    instance = service.start_instance(ORG_ID, definition["definition_id"], "document", "doc-1", created_by)
    return service, instance


def test_illegal_transition_is_rejected():
    service, instance = started_instance()
    try:
        service.execute_transition(instance["instance_id"], "missing", "approver-1", ["approver"])
        assert False
    except WorkflowTransitionError:
        pass
    assert service.get_instance(instance["instance_id"])["current_state"] == "draft"
    assert service.get_instance_history(instance["instance_id"]) == []


def test_wrong_role_is_rejected():
    service, instance = started_instance()
    try:
        service.execute_transition(instance["instance_id"], "approve", "reviewer-1", ["reviewer"])
        assert False
    except WorkflowPermissionError:
        pass
    assert service.get_instance(instance["instance_id"])["current_state"] == "draft"
    assert len(service.get_instance_history(instance["instance_id"])) == 0


def test_separation_of_duties_is_rejected():
    service, instance = started_instance("owner-1")
    try:
        service.execute_transition(instance["instance_id"], "approve", "owner-1", ["approver"])
        assert False
    except WorkflowSeparationOfDutiesError:
        pass
    assert service.get_instance(instance["instance_id"])["current_state"] == "draft"
    assert len(service.get_instance_history(instance["instance_id"])) == 0


def test_valid_transition_updates_state_and_appends_one_history_event():
    service, instance = started_instance("owner-1")
    updated = service.execute_transition(
        instance["instance_id"], "approve", "approver-1", ["approver"], "Looks good"
    )

    assert updated["current_state"] == "approved"
    assert updated["status"] == "completed"
    history = service.get_instance_history(instance["instance_id"])
    assert len(history) == 1
    event = history[0]
    assert event["transition_id"] == "approve"
    assert event["from_state"] == "draft"
    assert event["to_state"] == "approved"
    assert event["actor_id"] == "approver-1"
    assert event["actor_roles_at_time"] == ["approver"]
    assert event["comment"] == "Looks good"


def test_create_definition_versions_and_start_instance_is_idempotent():
    service = engine()
    first = service.create_definition(ORG_ID, "generic", STATES, TRANSITIONS, "admin-1", definition_id="def-1")
    second = service.create_definition(ORG_ID, "generic", STATES, TRANSITIONS, "admin-1")
    assert first["version"] == 1
    assert second["version"] == 2
    assert service.get_definition("def-1")["is_active"] is False
    assert second["is_active"] is True
    started = service.start_instance(ORG_ID, second["definition_id"], "document", "doc-9", "owner-1")
    again = service.start_instance(ORG_ID, second["definition_id"], "document", "doc-9", "owner-1")
    assert again["instance_id"] == started["instance_id"]


def test_admin_may_complete_own_submission_for_break_glass():
    service, instance = started_instance("owner-1")
    updated = service.execute_transition(instance["instance_id"], "approve", "owner-1", ["admin"])
    assert updated["current_state"] == "approved"


def test_list_instances_filters_and_paginates():
    service, first = started_instance("owner-1")
    definition_id = first["definition_id"]
    second = service.start_instance(ORG_ID, definition_id, "document", "doc-2", "owner-1")
    listed = service.list_instances(ORG_ID, entity_type="document", limit=1)
    assert len(listed["items"]) == 1
    assert listed["next_cursor"] in {first["instance_id"], second["instance_id"]}
    rest = service.list_instances(ORG_ID, entity_type="document", limit=1, cursor=listed["next_cursor"])
    assert len(rest["items"]) == 1
    assert rest["items"][0]["instance_id"] != listed["items"][0]["instance_id"]
