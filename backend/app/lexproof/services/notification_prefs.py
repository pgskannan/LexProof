"""Per-user notification preferences.

Two channels per notification type: in-app (fully wired -- respected by
VersionAnalysisService._create_notification, which skips writing a
notification a user has turned off) and email (stored so the preference is
captured, but this deployment has no outbound email/SMTP service configured
yet -- enabling it does not currently cause an email to be sent; the value
is preserved for when a mail sender is wired up).

Stored one document per user (doc_id = uid) in the ``notification_preferences``
collection, independent of organization -- a user's notification preferences
follow them across every org they belong to.
"""

from __future__ import annotations

from typing import Any, Callable

from ..repositories.firestore import FirestoreRepository

RepositoryFactory = Callable[[str], FirestoreRepository]

# type_ values written by VersionAnalysisService._create_notification.
NOTIFICATION_TYPES = ["analysis_complete", "analysis_failed"]

DEFAULT_NOTIFICATION_PREFERENCES: dict[str, bool] = {
    **{f"in_app_{type_}": True for type_ in NOTIFICATION_TYPES},
    **{f"email_{type_}": False for type_ in NOTIFICATION_TYPES},
}


def get_notification_preferences(repository_factory: RepositoryFactory, user_id: str) -> dict[str, Any]:
    """Return this user's notification preferences, defaults filled in."""
    try:
        repository = repository_factory("notification_preferences")
        record = repository.get(user_id) or {}
    except Exception:
        record = {}
    return {
        **DEFAULT_NOTIFICATION_PREFERENCES,
        **{key: bool(record[key]) for key in DEFAULT_NOTIFICATION_PREFERENCES if key in record},
    }


def update_notification_preferences(
    repository_factory: RepositoryFactory,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Merge ``updates`` (only known preference keys, non-None values) and persist."""
    current = get_notification_preferences(repository_factory, user_id)
    for key in DEFAULT_NOTIFICATION_PREFERENCES:
        value = updates.get(key)
        if value is not None:
            current[key] = bool(value)
    repository = repository_factory("notification_preferences")
    repository.set(user_id, current, merge=True)
    return current
