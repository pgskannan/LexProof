"""Chat (Slack/Teams) notification delivery-log and test-send endpoints.

Webhook URLs themselves are configured via the existing org settings
endpoints (`PATCH /orgs/{org_id}/settings`, `slack_webhook_url` /
`teams_webhook_url`) rather than duplicated here -- this module only exposes
what's specific to chat delivery: the read-only delivery log, and an
admin-only way to fire a test message without waiting for a real SLA
escalation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..services.auth import get_current_org_member, require_roles
from ..services.chat_notifications import ChatNotificationService, get_chat_notification_service
from ..services.roles import OrgRole

router = APIRouter(prefix="/orgs/{org_id}/chat-notifications", tags=["chat-notifications"])


def _service() -> ChatNotificationService:
    return get_chat_notification_service()


@router.get("/deliveries")
def list_chat_deliveries(
    org_id: str,
    limit: int = Query(50, ge=1, le=200),
    member: dict[str, Any] = Depends(get_current_org_member),
):
    """Any active member can see the delivery log -- it never contains the
    webhook URL itself, just what was (or would have been) sent."""
    return {"deliveries": _service().list_deliveries(org_id, limit=limit)}


@router.post("/test")
def send_test_chat_notification(
    org_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
):
    """Admin-only: fire a test message through whatever channel(s) are
    configured (or a simulated delivery if none are), so an admin can
    confirm a newly-pasted webhook URL actually works before relying on it
    for real SLA escalations."""
    require_roles(member, OrgRole.ADMIN.value)
    actor = member.get("email") or member.get("uid")
    deliveries = _service().notify_org(
        org_id,
        event_type="test",
        title="Test notification from LexProof",
        message=f"Triggered by {actor} to verify chat notification delivery is working.",
    )
    return {"deliveries": deliveries}
