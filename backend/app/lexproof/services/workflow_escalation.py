"""Bridges the generic workflow engine's SLA-escalation sweep to concrete
in-app notifications, without teaching the engine itself about
organizations, roles, or notifications -- it only knows how to find overdue
instances and invoke a callback naming the roles to tell.

There is no cron/scheduler process in this app, so the sweep is triggered
opportunistically: the Contract Reviews page calls it (best-effort, ignored
on failure) whenever someone opens it, which is the same page that surfaces
due dates and overdue badges. The real integration point for a production
deployment is unchanged either way -- an external scheduler (e.g. Cloud
Scheduler) can hit the same `POST /orgs/{org_id}/workflow-instances/escalate`
endpoint on a timer instead of relying on page visits.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from ..repositories.firestore import FirestoreRepository
from .chat_notifications import ChatNotificationService, get_chat_notification_service
from .organizations import MEMBER_ACTIVE, OrganizationService, get_organization_service
from .workflow_engine import WorkflowEngine, get_workflow_engine

logger = logging.getLogger(__name__)

# Best-effort human-readable destinations for a handful of known entity
# types. Anything else still gets a notification, just without a deep link.
_ENTITY_NOTIFICATION_URL: dict[str, str] = {
    "redline_proposal": "/dashboard/contracts/reviews",
}


class WorkflowEscalationService:
    def __init__(
        self,
        *,
        workflow: WorkflowEngine | None = None,
        organizations: OrganizationService | None = None,
        chat: ChatNotificationService | None = None,
        repository_factory: Callable[[str], FirestoreRepository] = FirestoreRepository,
    ) -> None:
        self.workflow = workflow or get_workflow_engine()
        self.organizations = organizations or get_organization_service()
        self.chat = chat or get_chat_notification_service()
        self.repository_factory = repository_factory

    def _notify_role_holders(
        self,
        instance: dict[str, Any],
        definition: dict[str, Any],
        roles: list[str],
    ) -> None:
        org_id = instance.get("org_id")
        if not org_id:
            return
        state = next(
            (item for item in definition.get("states") or [] if item.get("id") == instance.get("current_state")),
            {},
        )
        state_name = state.get("name") or instance.get("current_state") or "a workflow step"
        entity_type = instance.get("entity_type") or "item"
        contract_id = (instance.get("metadata") or {}).get("contract_id")
        url = _ENTITY_NOTIFICATION_URL.get(instance.get("entity_type") or "")
        title = f'"{state_name}" is overdue'
        message = (
            f"A {entity_type.replace('_', ' ')} has been waiting in \"{state_name}\" past its "
            "SLA and needs attention."
        )

        members = [
            member
            for member in self.organizations.list_members(org_id)
            if member.get("status") == MEMBER_ACTIVE and any(role in (member.get("roles") or []) for role in roles)
        ]
        if members:
            notifications = self.repository_factory("notifications")
            now = datetime.now(timezone.utc).isoformat()
            for member in members:
                user_id = member.get("user_id")
                if not user_id:
                    continue
                notification_id = str(uuid.uuid4())
                try:
                    notifications.set(notification_id, {
                        "id": notification_id,
                        "owner_id": user_id,
                        "type": "workflow_overdue",
                        "title": title,
                        "message": message,
                        "contract_id": contract_id,
                        "url": url,
                        "read": False,
                        "created_at": now,
                    })
                except Exception:
                    logger.warning(
                        "failed to write escalation notification user_id=%s instance_id=%s",
                        user_id, instance.get("instance_id"), exc_info=True,
                    )

        # Also post to the org's configured Slack/Teams channel(s) (or a
        # simulated delivery if none are configured) -- channel-wide, so
        # this fires even if no individual member currently holds one of
        # the escalated-to roles. Never allowed to break the sweep itself.
        try:
            self.chat.notify_org(org_id, event_type="workflow_overdue", title=title, message=message, url=url)
        except Exception:
            logger.warning(
                "chat notification failed for escalation org_id=%s instance_id=%s",
                org_id, instance.get("instance_id"), exc_info=True,
            )

    def sweep_org(self, org_id: str) -> list[dict[str, Any]]:
        """Escalate every not-yet-escalated overdue instance in this org and
        return what was escalated. Safe to call repeatedly -- already
        escalated instances are skipped until their next transition."""
        return self.workflow.escalate_overdue(org_id, notify=self._notify_role_holders)


_service: WorkflowEscalationService | None = None


def get_workflow_escalation_service() -> WorkflowEscalationService:
    global _service
    if _service is None:
        _service = WorkflowEscalationService()
    return _service
