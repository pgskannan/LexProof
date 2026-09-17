"""Generic Firestore-backed workflow engine. No contract-specific logic."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from ..repositories.firestore import FirestoreRepository
from .roles import ALL_ROLES, OrgRole, has_any_role

logger = logging.getLogger(__name__)

INSTANCE_IN_PROGRESS = "in_progress"
INSTANCE_COMPLETED = "completed"
INSTANCE_CANCELLED = "cancelled"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class WorkflowError(ValueError):
    """Base error for workflow engine failures."""


class WorkflowNotFoundError(WorkflowError):
    """Raised when a definition or instance does not exist."""


class WorkflowDefinitionError(WorkflowError):
    """Raised when a definition is invalid."""


class WorkflowTransitionError(WorkflowError):
    """Raised when a requested transition is illegal from the current state."""


class WorkflowPermissionError(WorkflowError):
    """Raised when the actor lacks an allowed role for the transition."""


class WorkflowSeparationOfDutiesError(WorkflowError):
    """Raised when the actor is forbidden by a requires_not_actor rule."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _available_roles(definition: dict[str, Any], current_state: str) -> list[str]:
    roles: list[str] = []
    for transition in definition.get("transitions") or []:
        if transition.get("from_state") != current_state:
            continue
        for role in transition.get("allowed_roles") or []:
            if role not in roles:
                roles.append(role)
    return roles


def _state_by_id(definition: dict[str, Any], state_id: str) -> dict[str, Any] | None:
    return next((state for state in definition.get("states") or [] if state.get("id") == state_id), None)


def _transition_by_id(definition: dict[str, Any], transition_id: str) -> dict[str, Any] | None:
    return next((item for item in definition.get("transitions") or [] if item.get("id") == transition_id), None)


def _sla_due_at(definition: dict[str, Any], state_id: str, from_iso: str) -> str | None:
    """An optional ``sla_hours`` on a state means "an instance should not sit in
    this state longer than this many hours" -- compute the resulting due
    timestamp, or None when the state has no SLA configured."""
    state = _state_by_id(definition, state_id) or {}
    hours = state.get("sla_hours")
    if not hours:
        return None
    try:
        from_dt = datetime.fromisoformat(from_iso)
    except (TypeError, ValueError):
        return None
    return (from_dt + timedelta(hours=float(hours))).isoformat()


def is_overdue(instance: dict[str, Any]) -> bool:
    """True when an in-progress instance has passed its current state's SLA
    due date. Terminal/cancelled instances and states with no SLA configured
    are never overdue."""
    if instance.get("status") != INSTANCE_IN_PROGRESS:
        return False
    due = instance.get("sla_due_at")
    if not due:
        return False
    try:
        due_dt = datetime.fromisoformat(due)
    except (TypeError, ValueError):
        return False
    if due_dt.tzinfo is None:
        due_dt = due_dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > due_dt


def validate_definition(states: list[dict[str, Any]], transitions: list[dict[str, Any]]) -> None:
    if not states:
        raise WorkflowDefinitionError("A workflow definition requires at least one state")
    state_ids = [state.get("id") for state in states]
    if any(not item for item in state_ids):
        raise WorkflowDefinitionError("Every state must have an id")
    if len(set(state_ids)) != len(state_ids):
        raise WorkflowDefinitionError("State ids must be unique")
    initials = [state for state in states if state.get("is_initial")]
    if len(initials) != 1:
        raise WorkflowDefinitionError("A workflow definition must have exactly one initial state")
    transition_ids = [item.get("id") for item in transitions]
    if any(not item for item in transition_ids):
        raise WorkflowDefinitionError("Every transition must have an id")
    if len(set(transition_ids)) != len(transition_ids):
        raise WorkflowDefinitionError("Transition ids must be unique")
    for transition in transitions:
        if transition.get("from_state") not in state_ids or transition.get("to_state") not in state_ids:
            raise WorkflowDefinitionError(f"Transition {transition.get('id')} references an unknown state")
        if not transition.get("action_name"):
            raise WorkflowDefinitionError(f"Transition {transition.get('id')} is missing action_name")
        for role in transition.get("allowed_roles") or []:
            if role not in ALL_ROLES:
                raise WorkflowDefinitionError(f"Unknown role in transition {transition.get('id')}: {role}")


class WorkflowEngine:
    def __init__(
        self,
        *,
        definitions: FirestoreRepository | None = None,
        instances: FirestoreRepository | None = None,
        history_factory: Callable[[str], FirestoreRepository] | None = None,
    ) -> None:
        self.definitions = definitions or FirestoreRepository("workflow_definitions")
        self.instances = instances or FirestoreRepository("workflow_instances")
        self._history_factory = history_factory or (
            lambda instance_id: FirestoreRepository(f"workflow_instances/{instance_id}/history")
        )

    def history(self, instance_id: str) -> FirestoreRepository:
        return self._history_factory(instance_id)

    def create_definition(
        self,
        org_id: str,
        name: str,
        states: list[dict[str, Any]],
        transitions: list[dict[str, Any]],
        created_by: str,
        *,
        definition_id: str | None = None,
    ) -> dict[str, Any]:
        validate_definition(states, transitions)
        existing = [
            item
            for item in self.definitions.stream()
            if item.get("org_id") == org_id and item.get("name") == name
        ]
        next_version = max((item.get("version") or 0) for item in existing) + 1 if existing else 1
        if definition_id:
            already = self.definitions.get(definition_id)
            if already:
                return already
        else:
            definition_id = str(uuid4())
        now = _now()
        for item in existing:
            if item.get("is_active"):
                self.definitions.set(item.get("definition_id") or item.get("id"), {"is_active": False, "updated_at": now}, merge=True)
        definition = {
            "definition_id": definition_id,
            "org_id": org_id,
            "name": name,
            "version": next_version,
            "is_active": True,
            "states": states,
            "transitions": transitions,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        self.definitions.set(definition_id, definition)
        logger.info("workflow definition created org_id=%s definition_id=%s name=%s version=%s actor=%s", org_id, definition_id, name, next_version, created_by)
        return definition

    def get_definition(self, definition_id: str) -> dict[str, Any]:
        definition = self.definitions.get(definition_id)
        if not definition:
            raise WorkflowNotFoundError(f"Workflow definition not found: {definition_id}")
        return {"definition_id": definition_id, **definition}

    def get_active_definition(self, org_id: str, name: str) -> dict[str, Any]:
        matches = [
            item
            for item in self.definitions.stream()
            if item.get("org_id") == org_id and item.get("name") == name and item.get("is_active")
        ]
        if not matches:
            raise WorkflowNotFoundError(f"No active workflow definition named {name}")
        matches.sort(key=lambda item: item.get("version") or 0, reverse=True)
        record = matches[0]
        return {"definition_id": record.get("definition_id") or record.get("id"), **record}

    def list_definitions(self, org_id: str, name: str | None = None) -> list[dict[str, Any]]:
        records = [
            {"definition_id": item.get("definition_id") or item.get("id"), **item}
            for item in self.definitions.stream()
            if item.get("org_id") == org_id and (name is None or item.get("name") == name)
        ]
        records.sort(key=lambda item: (item.get("name") or "", -(item.get("version") or 0)))
        return records

    def start_instance(
        self,
        org_id: str,
        definition_id: str,
        entity_type: str,
        entity_id: str,
        created_by: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.find_instance(org_id, entity_type, entity_id)
        if existing:
            return existing
        definition = self.get_definition(definition_id)
        if definition.get("org_id") != org_id:
            raise WorkflowNotFoundError(f"Workflow definition not found: {definition_id}")
        initial = next(state for state in definition["states"] if state.get("is_initial"))
        now = _now()
        instance_id = str(uuid4())
        instance = {
            "instance_id": instance_id,
            "org_id": org_id,
            "definition_id": definition_id,
            "definition_version": definition.get("version"),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "current_state": initial["id"],
            "status": INSTANCE_IN_PROGRESS,
            "available_roles": _available_roles(definition, initial["id"]),
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
            "state_entered_at": now,
            "sla_due_at": _sla_due_at(definition, initial["id"], now),
            "escalated_at": None,
        }
        self.instances.set(instance_id, instance)
        logger.info(
            "workflow instance started org_id=%s instance_id=%s definition_id=%s entity_type=%s entity_id=%s actor=%s",
            org_id, instance_id, definition_id, entity_type, entity_id, created_by,
        )
        return instance

    def find_instance(self, org_id: str, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        matches = []
        if hasattr(self.instances, "query"):
            try:
                matches = self.instances.query(equal={"org_id": org_id, "entity_type": entity_type, "entity_id": entity_id}, limit=1)
            except Exception:
                matches = []
        if not matches:
            matches = [
                item
                for item in self.instances.stream()
                if item.get("org_id") == org_id and item.get("entity_type") == entity_type and item.get("entity_id") == entity_id
            ]
        if not matches:
            return None
        item = matches[0]
        return {"instance_id": item.get("instance_id") or item.get("id"), **item}

    def get_instance(self, instance_id: str) -> dict[str, Any]:
        instance = self.instances.get(instance_id)
        if not instance:
            raise WorkflowNotFoundError(f"Workflow instance not found: {instance_id}")
        return {"instance_id": instance_id, **instance}

    def assert_transition_allowed(
        self,
        instance_id: str,
        transition_id: str,
        actor_id: str,
        actor_roles: list[str],
    ) -> dict[str, Any]:
        instance = self.get_instance(instance_id)
        definition = self.get_definition(instance["definition_id"])
        return self._validate_transition(instance, definition, transition_id, actor_id, actor_roles)

    def _validate_transition(
        self,
        instance: dict[str, Any],
        definition: dict[str, Any],
        transition_id: str,
        actor_id: str,
        actor_roles: list[str],
    ) -> dict[str, Any]:
        transition = _transition_by_id(definition, transition_id)
        if not transition:
            raise WorkflowTransitionError(f"Unknown transition: {transition_id}")
        current_state = instance.get("current_state")
        instance_id = instance.get("instance_id")
        if transition.get("from_state") != current_state:
            logger.warning(
                "permission denied org_id=%s actor=%s action=illegal_transition instance_id=%s from=%s requested=%s",
                instance.get("org_id"), actor_id, instance_id, current_state, transition_id,
            )
            raise WorkflowTransitionError(
                f"Transition {transition_id} is not legal from state {current_state}"
            )
        allowed = list(transition.get("allowed_roles") or [])
        if not has_any_role(actor_roles, allowed):
            logger.warning(
                "permission denied org_id=%s actor=%s action=wrong_role instance_id=%s transition_id=%s required=%s held=%s",
                instance.get("org_id"), actor_id, instance_id, transition_id, allowed, actor_roles,
            )
            raise WorkflowPermissionError(
                f"Role {', '.join(actor_roles) or 'none'} cannot perform {transition.get('action_name')}"
            )
        if OrgRole.ADMIN.value not in actor_roles:
            for field_ref in transition.get("requires_not_actor") or []:
                forbidden = instance.get(field_ref)
                if forbidden and forbidden == actor_id:
                    logger.warning(
                        "permission denied org_id=%s actor=%s action=separation_of_duties instance_id=%s field=%s",
                        instance.get("org_id"), actor_id, instance_id, field_ref,
                    )
                    raise WorkflowSeparationOfDutiesError(
                        f"Actor cannot perform {transition.get('action_name')} because they are recorded as {field_ref}"
                    )
        return transition

    def execute_transition(
        self,
        instance_id: str,
        transition_id: str,
        actor_id: str,
        actor_roles: list[str],
        comment: str | None = None,
    ) -> dict[str, Any]:
        def apply(transaction: Any) -> dict[str, Any]:
            instance = self.instances.get(instance_id, transaction=transaction)
            if not instance:
                raise WorkflowNotFoundError(f"Workflow instance not found: {instance_id}")
            instance = {"instance_id": instance_id, **instance}
            definition = self.get_definition(instance["definition_id"])
            transition = self._validate_transition(instance, definition, transition_id, actor_id, actor_roles)
            to_state = transition["to_state"]
            state = _state_by_id(definition, to_state) or {}
            now = _now()
            updates = {
                "current_state": to_state,
                "status": INSTANCE_COMPLETED if state.get("is_terminal") else INSTANCE_IN_PROGRESS,
                "available_roles": _available_roles(definition, to_state),
                "updated_at": now,
                "updated_by": actor_id,
                "state_entered_at": now,
                "sla_due_at": _sla_due_at(definition, to_state, now),
                "escalated_at": None,
            }
            event_id = str(uuid4())
            event = {
                "event_id": event_id,
                "instance_id": instance_id,
                "transition_id": transition_id,
                "from_state": instance.get("current_state"),
                "to_state": to_state,
                "actor_id": actor_id,
                "actor_roles_at_time": list(actor_roles),
                "comment": comment,
                "occurred_at": now,
            }
            self.instances.set(instance_id, updates, merge=True, transaction=transaction)
            self.history(instance_id).set(event_id, event, transaction=transaction)
            logger.info(
                "workflow transition org_id=%s instance_id=%s actor=%s action=%s from=%s to=%s",
                instance.get("org_id"), instance_id, actor_id, transition_id, instance.get("current_state"), to_state,
            )
            return {**instance, **updates}

        if hasattr(self.instances, "run_transaction"):
            return self.instances.run_transaction(apply)
        return apply(None)

    def get_instance_history(self, instance_id: str) -> list[dict[str, Any]]:
        self.get_instance(instance_id)
        events = list(self.history(instance_id).stream())
        events.sort(key=lambda item: item.get("occurred_at") or "")
        return events

    def list_instances(
        self,
        org_id: str,
        entity_type: str | None = None,
        status: str | None = None,
        assigned_role: str | None = None,
        *,
        entity_id: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        page_size = min(max(limit, 1), MAX_PAGE_SIZE)
        queried = False
        records: list[dict[str, Any]] = []
        if hasattr(self.instances, "query"):
            equal: dict[str, Any] = {"org_id": org_id}
            if entity_type:
                equal["entity_type"] = entity_type
            if status:
                equal["status"] = status
            if entity_id:
                equal["entity_id"] = entity_id
            try:
                kwargs: dict[str, Any] = {"equal": equal, "order_by": "created_at", "descending": True}
                if assigned_role:
                    kwargs["array_contains"] = ("available_roles", assigned_role)
                records = self.instances.query(**kwargs)
                queried = True
            except Exception as exc:
                logger.warning("workflow instance query failed org_id=%s: %s", org_id, exc)
        if not queried:
            records = [
                {"instance_id": item.get("instance_id") or item.get("id"), **item}
                for item in self.instances.stream()
                if item.get("org_id") == org_id
                and (entity_type is None or item.get("entity_type") == entity_type)
                and (status is None or item.get("status") == status)
                and (entity_id is None or item.get("entity_id") == entity_id)
                and (assigned_role is None or assigned_role in (item.get("available_roles") or []))
            ]
        else:
            records = [{"instance_id": item.get("instance_id") or item.get("id"), **item} for item in records]
            if assigned_role:
                records = [item for item in records if assigned_role in (item.get("available_roles") or [])]
        records.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        start = 0
        if cursor:
            for index, item in enumerate(records):
                if item.get("instance_id") == cursor:
                    start = index + 1
                    break
        page = records[start:start + page_size]
        next_cursor = page[-1]["instance_id"] if len(page) == page_size and start + page_size < len(records) else None
        return {"items": page, "next_cursor": next_cursor}


    def update_definition_content(
        self,
        definition_id: str,
        states: list[dict[str, Any]],
        transitions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Refresh a definition's states/transitions in place -- same
        definition_id and version, so in-flight instances (which reference
        this definition_id directly) are unaffected. Used to pick up
        additive annotation changes -- e.g. newly configured SLA hours or
        escalation roles -- on a definition that was already provisioned for
        an org, without spawning an ever-growing chain of versions for
        metadata-only edits."""
        validate_definition(states, transitions)
        definition = self.get_definition(definition_id)
        updates = {"states": states, "transitions": transitions, "updated_at": _now()}
        self.definitions.set(definition_id, updates, merge=True)
        return {**definition, **updates}

    def list_overdue_instances(self, org_id: str) -> list[dict[str, Any]]:
        """Every in-progress instance in this org that has passed its
        current state's SLA due date."""
        page = self.list_instances(org_id, status=INSTANCE_IN_PROGRESS, limit=MAX_PAGE_SIZE)
        return [item for item in page["items"] if is_overdue(item)]

    def escalate_overdue(
        self,
        org_id: str,
        *,
        notify: Callable[[dict[str, Any], dict[str, Any], list[str]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Find overdue instances that have not yet been escalated, mark
        each escalated (idempotent -- an already-escalated instance is
        skipped until its next transition resets the flag), and invoke
        ``notify(instance, definition, escalate_to_roles)`` for each one
        whose current state names roles to escalate to. This engine stays
        generic: it has no idea what a notification is, only that the
        caller-supplied callback should be told who to tell."""
        escalated: list[dict[str, Any]] = []
        for instance in self.list_overdue_instances(org_id):
            if instance.get("escalated_at"):
                continue
            definition = self.get_definition(instance["definition_id"])
            state = _state_by_id(definition, instance["current_state"]) or {}
            roles = list(state.get("escalate_to_roles") or [])
            now = _now()
            self.instances.set(instance["instance_id"], {"escalated_at": now}, merge=True)
            instance = {**instance, "escalated_at": now}
            if roles and notify:
                try:
                    notify(instance, definition, roles)
                except Exception:
                    logger.warning(
                        "escalation notify callback failed instance_id=%s", instance["instance_id"], exc_info=True,
                    )
            escalated.append(instance)
            logger.info(
                "workflow instance escalated org_id=%s instance_id=%s state=%s roles=%s",
                org_id, instance["instance_id"], instance["current_state"], roles,
            )
        return escalated


def get_workflow_engine() -> WorkflowEngine:
    return WorkflowEngine()
