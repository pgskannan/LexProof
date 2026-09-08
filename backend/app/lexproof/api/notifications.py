"""In-app notifications for the signed-in user.

Notifications are written by VersionAnalysisService (analysis complete /
failed) into the ``notifications`` Firestore collection; this module only
reads and updates them for the caller. There is no cross-user visibility --
every notification is scoped to its owner_id, unlike most other collections
in this app which treat a missing owner_id as a legacy/visible-to-all record
(notifications never have a missing owner_id since they are only ever
written with one).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    message: str
    contract_id: Optional[str] = None
    url: Optional[str] = None
    read: bool = False
    created_at: Optional[datetime] = None


def _response(record: dict[str, Any]) -> NotificationResponse:
    return NotificationResponse(
        id=str(record.get("id") or ""),
        type=str(record.get("type") or ""),
        title=str(record.get("title") or ""),
        message=str(record.get("message") or ""),
        contract_id=record.get("contract_id"),
        url=record.get("url"),
        read=bool(record.get("read", False)),
        created_at=record.get("created_at"),
    )


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[NotificationResponse]:
    """Return the signed-in user's notifications, most recent first."""
    uid = str(user["uid"])
    repository = FirestoreRepository("notifications")
    records = [
        record for record in repository.stream()
        if record.get("owner_id") == uid and (not unread_only or not record.get("read"))
    ]
    records.sort(key=lambda record: record.get("created_at") or "", reverse=True)
    return [_response(record) for record in records[:limit]]


@router.get("/unread-count")
def unread_count(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, int]:
    uid = str(user["uid"])
    repository = FirestoreRepository("notifications")
    count = sum(1 for record in repository.stream() if record.get("owner_id") == uid and not record.get("read"))
    return {"count": count}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: str, user: dict[str, Any] = Depends(get_current_user)) -> NotificationResponse:
    uid = str(user["uid"])
    repository = FirestoreRepository("notifications")
    record = repository.get(notification_id)
    if not record or record.get("owner_id") != uid:
        raise HTTPException(status_code=404, detail="Notification not found")
    repository.set(notification_id, {"read": True}, merge=True)
    return _response({**record, "read": True})


@router.post("/read-all")
def mark_all_read(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, int]:
    uid = str(user["uid"])
    repository = FirestoreRepository("notifications")
    updated = 0
    for record in repository.stream():
        if record.get("owner_id") == uid and not record.get("read"):
            repository.set(record["id"], {"read": True}, merge=True)
            updated += 1
    return {"updated": updated}
