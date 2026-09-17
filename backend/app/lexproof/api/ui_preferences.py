"""Per-user UI preferences endpoint: theme, dashboard widget layout, and
onboarding-tour completion."""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..repositories.firestore import FirestoreRepository
from ..services.auth import get_current_user
from ..services.ui_prefs import get_ui_preferences, update_ui_preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


class DashboardWidgetPref(BaseModel):
    id: str
    visible: bool


class UiPreferencesResponse(BaseModel):
    theme: str
    dashboard_widgets: List[DashboardWidgetPref]
    tour_completed: bool


class UpdateUiPreferencesRequest(BaseModel):
    theme: Optional[str] = None
    dashboard_widgets: Optional[List[DashboardWidgetPref]] = None
    tour_completed: Optional[bool] = None


@router.get("/ui", response_model=UiPreferencesResponse)
def get_preferences(user: dict[str, Any] = Depends(get_current_user)) -> UiPreferencesResponse:
    """Return the signed-in user's UI preferences (defaults filled in)."""
    uid = str(user["uid"])
    prefs = get_ui_preferences(FirestoreRepository, uid)
    return UiPreferencesResponse(**prefs)


@router.patch("/ui", response_model=UiPreferencesResponse)
def update_preferences(
    body: UpdateUiPreferencesRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> UiPreferencesResponse:
    """Update the signed-in user's UI preferences."""
    uid = str(user["uid"])
    updates = body.model_dump(exclude_none=True)
    prefs = update_ui_preferences(FirestoreRepository, uid, updates)
    return UiPreferencesResponse(**prefs)
