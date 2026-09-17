"""Teams / Slack chat notifications (stub-now, real-webhook-later).

Unlike the e-signature integration (`esignature.py`), which is gated on a
single set of *global* provider credentials, chat notifications are gated
per-organization: each org optionally configures its own Slack and/or
Microsoft Teams incoming-webhook URL in Organization settings
(`slack_webhook_url` / `teams_webhook_url`, see `services/organizations.py`).
Both webhook flavors accept the same minimal JSON body
(``{"text": "..."}``) so one payload shape serves both without a
provider-specific SDK.

Per this engagement's "stub-now, wire in real credentials later" scope
decision:

- When an org has configured at least one webhook URL, `notify_org()` makes
  a real HTTP POST to it (via `httpx`) and records the outcome (success or
  failure -- a bad/expired webhook URL never raises, it just logs a failed
  delivery so the caller's own flow is never blocked by a notification
  problem).
- When an org has configured neither, `notify_org()` still records exactly
  one *simulated* delivery (provider="stub") carrying the message that would
  have been sent, so the feature -- and its delivery log -- is fully
  demoable with zero configuration, exactly like the e-signature stub.

Every attempt (real or simulated) is persisted to the
``chat_notification_deliveries`` collection so an org admin can see what was
sent (or would have been sent) from the settings page, without needing
actual access to the destination Slack/Teams channel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import uuid4

import httpx

from ..repositories.firestore import FirestoreRepository
from .organizations import OrganizationService, get_organization_service

logger = logging.getLogger(__name__)

DELIVERIES_COLLECTION = "chat_notification_deliveries"
WEBHOOK_SETTINGS_KEYS = ("slack_webhook_url", "teams_webhook_url")
_CHANNEL_NAMES: dict[str, str] = {"slack_webhook_url": "slack", "teams_webhook_url": "teams"}
HttpPost = Callable[[str, dict[str, Any]], "httpx.Response"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_post(url: str, payload: dict[str, Any]) -> httpx.Response:
    return httpx.post(url, json=payload, timeout=10.0)


def build_payload(title: str, message: str, url: str | None) -> dict[str, Any]:
    """Slack- and Teams-incoming-webhook-compatible payload. Both accept a
    bare ``{"text": ...}`` body; Markdown-style bold (``*title*``) renders
    correctly in Slack and degrades gracefully (shows the asterisks) in
    Teams, which is an acceptable tradeoff for keeping one payload shape."""
    text = f"*{title}*\n{message}"
    if url:
        text += f"\n{url}"
    return {"text": text}


class ChatNotificationService:
    def __init__(
        self,
        *,
        organizations: OrganizationService | None = None,
        deliveries: FirestoreRepository | None = None,
        http_post: HttpPost | None = None,
    ) -> None:
        self.organizations = organizations or get_organization_service()
        self.deliveries = deliveries or FirestoreRepository(DELIVERIES_COLLECTION)
        self._post = http_post or _default_post

    def _configured_channels(self, org_id: str) -> list[tuple[str, str]]:
        settings = self.organizations.get_org_settings(org_id)
        channels: list[tuple[str, str]] = []
        for key in WEBHOOK_SETTINGS_KEYS:
            value = settings.get(key)
            if value:
                channels.append((_CHANNEL_NAMES[key], str(value)))
        return channels

    def notify_org(
        self,
        org_id: str,
        *,
        event_type: str,
        title: str,
        message: str,
        url: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Deliver (or simulate) a chat notification to every channel this
        org has configured. Always returns at least one delivery record --
        real deliveries for each configured channel, or a single simulated
        one when nothing is configured -- and never raises: a broken
        webhook or network hiccup is recorded as a failed delivery, not
        propagated to the caller."""
        channels = self._configured_channels(org_id)
        payload = build_payload(title, message, url)
        records: list[dict[str, Any]] = []

        if not channels:
            records.append(
                self._record(
                    org_id,
                    channel="none_configured",
                    provider="stub",
                    status="simulated",
                    event_type=event_type,
                    title=title,
                    message=message,
                    url=url,
                    detail="No Slack or Teams webhook is configured for this org yet -- this delivery was simulated. "
                    "Configure a webhook URL in Organization settings to send it for real.",
                )
            )
            return records

        for channel, webhook_url in channels:
            try:
                response = self._post(webhook_url, payload)
                ok = 200 <= response.status_code < 300
                records.append(
                    self._record(
                        org_id,
                        channel=channel,
                        provider=channel,
                        status="sent" if ok else "failed",
                        event_type=event_type,
                        title=title,
                        message=message,
                        url=url,
                        detail=None if ok else f"HTTP {response.status_code}: {response.text[:500]}",
                    )
                )
            except Exception as exc:  # network error, bad URL, timeout, etc.
                logger.warning("chat notification delivery failed org_id=%s channel=%s: %s", org_id, channel, exc)
                records.append(
                    self._record(
                        org_id,
                        channel=channel,
                        provider=channel,
                        status="failed",
                        event_type=event_type,
                        title=title,
                        message=message,
                        url=url,
                        detail=str(exc)[:500],
                    )
                )
        return records

    def list_deliveries(self, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = [row for row in self.deliveries.stream() if row.get("org_id") == org_id]
        rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        if limit and len(rows) > limit:
            rows = rows[:limit]
        return rows

    def _record(
        self,
        org_id: str,
        *,
        channel: str,
        provider: str,
        status: str,
        event_type: str,
        title: str,
        message: str,
        url: str | None,
        detail: str | None,
    ) -> dict[str, Any]:
        delivery_id = str(uuid4())
        record = {
            "delivery_id": delivery_id,
            "org_id": org_id,
            "channel": channel,
            "provider": provider,
            "status": status,
            "event_type": event_type,
            "title": title,
            "message": message,
            "url": url,
            "detail": detail,
            "created_at": _now_iso(),
        }
        try:
            self.deliveries.set(delivery_id, record)
        except Exception:
            logger.warning("failed to persist chat delivery record org_id=%s channel=%s", org_id, channel, exc_info=True)
        return record


_service: ChatNotificationService | None = None


def get_chat_notification_service() -> ChatNotificationService:
    global _service
    if _service is None:
        _service = ChatNotificationService()
    return _service
