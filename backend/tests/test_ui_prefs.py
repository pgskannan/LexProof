"""Unit tests for services/ui_prefs.py."""

from app.lexproof.services.ui_prefs import (
    DEFAULT_UI_PREFERENCES,
    get_ui_preferences,
    update_ui_preferences,
)
from tests.fakes import FakeRepository


def reset_stores():
    FakeRepository.stores = {"ui_preferences": {}}


def test_defaults_to_system_theme():
    reset_stores()
    prefs = get_ui_preferences(FakeRepository, "user-1")
    assert prefs == DEFAULT_UI_PREFERENCES
    assert prefs["theme"] == "system"


def test_defaults_to_all_widgets_visible_in_default_order():
    reset_stores()
    prefs = get_ui_preferences(FakeRepository, "user-1")
    ids = [w["id"] for w in prefs["dashboard_widgets"]]
    assert ids == ["stat-contracts", "stat-passports", "stat-findings", "recent-activity"]
    assert all(w["visible"] for w in prefs["dashboard_widgets"])


def test_defaults_to_tour_not_completed():
    reset_stores()
    prefs = get_ui_preferences(FakeRepository, "user-1")
    assert prefs["tour_completed"] is False


def test_update_persists_a_valid_theme():
    reset_stores()
    update_ui_preferences(FakeRepository, "user-1", {"theme": "dark"})
    assert get_ui_preferences(FakeRepository, "user-1")["theme"] == "dark"


def test_update_ignores_an_invalid_theme_value():
    reset_stores()
    update_ui_preferences(FakeRepository, "user-1", {"theme": "dark"})
    update_ui_preferences(FakeRepository, "user-1", {"theme": "psychedelic"})
    assert get_ui_preferences(FakeRepository, "user-1")["theme"] == "dark"


def test_preferences_are_per_user():
    reset_stores()
    update_ui_preferences(FakeRepository, "user-a", {"theme": "dark"})
    assert get_ui_preferences(FakeRepository, "user-a")["theme"] == "dark"
    assert get_ui_preferences(FakeRepository, "user-b")["theme"] == "system"


def test_update_persists_widget_reorder_and_visibility():
    reset_stores()
    reordered = [
        {"id": "recent-activity", "visible": True},
        {"id": "stat-findings", "visible": False},
        {"id": "stat-contracts", "visible": True},
        {"id": "stat-passports", "visible": True},
    ]
    update_ui_preferences(FakeRepository, "user-1", {"dashboard_widgets": reordered})
    stored = get_ui_preferences(FakeRepository, "user-1")["dashboard_widgets"]
    assert stored == reordered


def test_update_ignores_malformed_widget_list():
    reset_stores()
    update_ui_preferences(FakeRepository, "user-1", {"dashboard_widgets": "not-a-list"})
    prefs = get_ui_preferences(FakeRepository, "user-1")
    assert prefs["dashboard_widgets"] == DEFAULT_UI_PREFERENCES["dashboard_widgets"]


def test_update_ignores_widget_list_with_unknown_id():
    reset_stores()
    update_ui_preferences(
        FakeRepository,
        "user-1",
        {"dashboard_widgets": [{"id": "not-a-real-widget", "visible": True}]},
    )
    prefs = get_ui_preferences(FakeRepository, "user-1")
    assert prefs["dashboard_widgets"] == DEFAULT_UI_PREFERENCES["dashboard_widgets"]


def test_update_fills_in_missing_widgets_as_visible():
    reset_stores()
    update_ui_preferences(
        FakeRepository,
        "user-1",
        {"dashboard_widgets": [{"id": "stat-contracts", "visible": False}]},
    )
    stored = get_ui_preferences(FakeRepository, "user-1")["dashboard_widgets"]
    by_id = {w["id"]: w["visible"] for w in stored}
    assert by_id["stat-contracts"] is False
    assert by_id["stat-passports"] is True
    assert by_id["stat-findings"] is True
    assert by_id["recent-activity"] is True


def test_update_persists_tour_completed():
    reset_stores()
    update_ui_preferences(FakeRepository, "user-1", {"tour_completed": True})
    assert get_ui_preferences(FakeRepository, "user-1")["tour_completed"] is True


def test_update_ignores_non_boolean_tour_completed():
    reset_stores()
    update_ui_preferences(FakeRepository, "user-1", {"tour_completed": "yes"})
    assert get_ui_preferences(FakeRepository, "user-1")["tour_completed"] is False


def test_tour_completed_is_per_user():
    reset_stores()
    update_ui_preferences(FakeRepository, "user-a", {"tour_completed": True})
    assert get_ui_preferences(FakeRepository, "user-a")["tour_completed"] is True
    assert get_ui_preferences(FakeRepository, "user-b")["tour_completed"] is False
