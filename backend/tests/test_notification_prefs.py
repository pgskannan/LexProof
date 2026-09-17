"""Unit tests for services/notification_prefs.py and its wiring into
VersionAnalysisService._create_notification (the in-app "off" preference
must suppress the notification write, matching the feature's contract that
in-app preferences are actually respected, not just stored)."""

from app.lexproof.services.notification_prefs import (
    DEFAULT_NOTIFICATION_PREFERENCES,
    get_notification_preferences,
    update_notification_preferences,
)
from app.lexproof.services.version_analysis import VersionAnalysisService
from tests.fakes import FakeRepository


def reset_stores():
    FakeRepository.stores = {"notification_preferences": {}, "notifications": {}}


def test_defaults_are_in_app_on_email_off():
    reset_stores()
    prefs = get_notification_preferences(FakeRepository, "user-1")
    assert prefs == DEFAULT_NOTIFICATION_PREFERENCES
    assert prefs["in_app_analysis_complete"] is True
    assert prefs["email_analysis_complete"] is False


def test_update_merges_only_known_keys_and_ignores_none():
    reset_stores()
    update_notification_preferences(FakeRepository, "user-1", {"in_app_analysis_failed": False, "bogus_key": True})
    prefs = get_notification_preferences(FakeRepository, "user-1")
    assert prefs["in_app_analysis_failed"] is False
    assert "bogus_key" not in prefs
    # A second update with an explicit None for an untouched key doesn't clobber it.
    update_notification_preferences(FakeRepository, "user-1", {"email_analysis_complete": None})
    prefs_again = get_notification_preferences(FakeRepository, "user-1")
    assert prefs_again["in_app_analysis_failed"] is False


def test_preferences_are_per_user():
    reset_stores()
    update_notification_preferences(FakeRepository, "user-a", {"in_app_analysis_complete": False})
    assert get_notification_preferences(FakeRepository, "user-a")["in_app_analysis_complete"] is False
    assert get_notification_preferences(FakeRepository, "user-b")["in_app_analysis_complete"] is True


def _service() -> VersionAnalysisService:
    return VersionAnalysisService(
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        repository_factory=FakeRepository,
    )


def test_create_notification_writes_by_default():
    reset_stores()
    service = _service()
    service._create_notification(
        user_id="user-1",
        type_="analysis_complete",
        title="Done",
        message="msg",
    )
    written = list(FakeRepository("notifications").stream())
    assert len(written) == 1
    assert written[0]["owner_id"] == "user-1"


def test_create_notification_suppressed_when_in_app_preference_off():
    reset_stores()
    update_notification_preferences(FakeRepository, "user-1", {"in_app_analysis_complete": False})
    service = _service()
    service._create_notification(
        user_id="user-1",
        type_="analysis_complete",
        title="Done",
        message="msg",
    )
    assert list(FakeRepository("notifications").stream()) == []


def test_create_notification_for_other_type_still_written_when_only_one_type_disabled():
    reset_stores()
    update_notification_preferences(FakeRepository, "user-1", {"in_app_analysis_complete": False})
    service = _service()
    service._create_notification(
        user_id="user-1",
        type_="analysis_failed",
        title="Failed",
        message="msg",
    )
    written = list(FakeRepository("notifications").stream())
    assert len(written) == 1
    assert written[0]["type"] == "analysis_failed"
