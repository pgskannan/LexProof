"""Per-user UI preferences: color theme, dashboard widget layout, and
whether the first-run onboarding tour has been completed.

Stored one document per user (doc_id = uid) in the ``ui_preferences``
collection, independent of organization -- like notification preferences,
this follows the user across every org they belong to and every device they
sign in on, rather than living in browser localStorage alone.
"""

from __future__ import annotations

from typing import Any, Callable

from ..repositories.firestore import FirestoreRepository

RepositoryFactory = Callable[[str], FirestoreRepository]

THEME_VALUES = ["light", "dark", "system"]

# The dashboard's customizable widgets, in their default order. A user's
# stored ``dashboard_widgets`` list is an ordering of these ids plus a
# per-widget ``visible`` flag -- reordering the list reorders the dashboard,
# and ``visible: false`` hides a widget without losing its position.
DASHBOARD_WIDGET_IDS = ["stat-contracts", "stat-passports", "stat-findings", "recent-activity"]
DEFAULT_DASHBOARD_WIDGETS: list[dict[str, Any]] = [
    {"id": widget_id, "visible": True} for widget_id in DASHBOARD_WIDGET_IDS
]

DEFAULT_UI_PREFERENCES: dict[str, Any] = {
    "theme": "system",
    "dashboard_widgets": DEFAULT_DASHBOARD_WIDGETS,
    "tour_completed": False,
}


def _normalize_widgets(value: Any) -> list[dict[str, Any]] | None:
    """Validate a candidate ``dashboard_widgets`` value.

    Returns a clean list (known ids only, deduped, missing ids appended as
    visible) or ``None`` if ``value`` isn't a usable list at all -- callers
    fall back to the default in that case rather than persisting garbage.
    """
    if not isinstance(value, list):
        return None
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        widget_id = entry.get("id")
        visible = entry.get("visible")
        if widget_id not in DASHBOARD_WIDGET_IDS or not isinstance(visible, bool):
            return None
        if widget_id in seen:
            continue
        seen.add(widget_id)
        result.append({"id": widget_id, "visible": visible})
    for widget_id in DASHBOARD_WIDGET_IDS:
        if widget_id not in seen:
            result.append({"id": widget_id, "visible": True})
    return result


def get_ui_preferences(repository_factory: RepositoryFactory, user_id: str) -> dict[str, Any]:
    """Return this user's UI preferences, defaults filled in."""
    try:
        repository = repository_factory("ui_preferences")
        record = repository.get(user_id) or {}
    except Exception:
        record = {}
    theme = record.get("theme")
    if theme not in THEME_VALUES:
        theme = DEFAULT_UI_PREFERENCES["theme"]
    widgets = _normalize_widgets(record.get("dashboard_widgets"))
    if widgets is None:
        widgets = [dict(w) for w in DEFAULT_DASHBOARD_WIDGETS]
    tour_completed = record.get("tour_completed")
    if not isinstance(tour_completed, bool):
        tour_completed = DEFAULT_UI_PREFERENCES["tour_completed"]
    return {"theme": theme, "dashboard_widgets": widgets, "tour_completed": tour_completed}


def update_ui_preferences(
    repository_factory: RepositoryFactory,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Merge valid ``theme``/``dashboard_widgets``/``tour_completed`` values and persist."""
    current = get_ui_preferences(repository_factory, user_id)
    theme = updates.get("theme")
    if theme in THEME_VALUES:
        current["theme"] = theme
    if "dashboard_widgets" in updates:
        widgets = _normalize_widgets(updates.get("dashboard_widgets"))
        if widgets is not None:
            current["dashboard_widgets"] = widgets
    if isinstance(updates.get("tour_completed"), bool):
        current["tour_completed"] = updates["tour_completed"]
    repository = repository_factory("ui_preferences")
    repository.set(user_id, current, merge=True)
    return current
