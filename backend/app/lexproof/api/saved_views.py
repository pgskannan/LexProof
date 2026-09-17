"""Per-user saved filter views for list pages (Contracts, Findings & Redlines,
...). A "view" is just a named snapshot of whatever filter state a page's
own filter bar produces -- this module has no idea what a "severity" or
"status" filter means, it only stores and returns an opaque ``filters``
object scoped by the page it belongs to.

Stored in the ``saved_views`` collection, owner-scoped like notifications
(never visible cross-user, unlike most collections in this app which treat
a missing owner_id as legacy/visible-to-all).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_user

router = APIRouter(prefix="/saved-views", tags=["saved-views"])

MAX_VIEWS_PER_PAGE = 25


class SavedViewResponse(BaseModel):
    id: str
    page: str
    name: str
    filters: dict[str, Any]
    created_at: Optional[datetime] = None


class CreateSavedViewRequest(BaseModel):
    page: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=60)
    filters: dict[str, Any] = Field(default_factory=dict)


def _response(record: dict[str, Any]) -> SavedViewResponse:
    return SavedViewResponse(
        id=str(record.get("id") or ""),
        page=str(record.get("page") or ""),
        name=str(record.get("name") or ""),
        filters=record.get("filters") or {},
        created_at=record.get("created_at"),
    )


@router.get("", response_model=list[SavedViewResponse])
def list_saved_views(
    page: str = Query(..., min_length=1, max_length=40),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[SavedViewResponse]:
    """Return the signed-in user's saved views for one page, oldest first."""
    uid = str(user["uid"])
    repository = FirestoreRepository("saved_views")
    records = [
        record for record in repository.stream()
        if record.get("owner_id") == uid and record.get("page") == page
    ]
    records.sort(key=lambda record: record.get("created_at") or "")
    return [_response(record) for record in records]


@router.post("", response_model=SavedViewResponse, status_code=201)
def create_saved_view(
    body: CreateSavedViewRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> SavedViewResponse:
    uid = str(user["uid"])
    repository = FirestoreRepository("saved_views")
    existing = [
        record for record in repository.stream()
        if record.get("owner_id") == uid and record.get("page") == body.page
    ]
    if len(existing) >= MAX_VIEWS_PER_PAGE:
        raise HTTPException(status_code=400, detail=f"You can save at most {MAX_VIEWS_PER_PAGE} views per page")
    view_id = str(uuid.uuid4())
    record = {
        "id": view_id,
        "owner_id": uid,
        "page": body.page,
        "name": body.name.strip(),
        "filters": body.filters,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    repository.set(view_id, record)
    return _response(record)


@router.delete("/{view_id}", status_code=204)
def delete_saved_view(view_id: str, user: dict[str, Any] = Depends(get_current_user)) -> None:
    uid = str(user["uid"])
    repository = FirestoreRepository("saved_views")
    record = repository.get(view_id)
    if not record or record.get("owner_id") != uid:
        raise HTTPException(status_code=404, detail="Saved view not found")
    repository.delete(view_id)
