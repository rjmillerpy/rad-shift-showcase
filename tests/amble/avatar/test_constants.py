"""Constants surface — locks the shape so future edits don't silently drift."""

import pytest

from app.amble.avatar import constants


@pytest.mark.parametrize(
    "name,value,min_value",
    [
        ("MIN_ATTRIBUTE_LENGTH", constants.MIN_ATTRIBUTE_LENGTH, 1),
        ("MAX_ATTRIBUTE_LENGTH", constants.MAX_ATTRIBUTE_LENGTH, constants.MIN_ATTRIBUTE_LENGTH),
    ],
)
def test_attribute_bounds_are_positive_and_ordered(name: str, value: int, min_value: int) -> None:
    assert isinstance(value, int), name
    assert value >= min_value, name


def test_allowed_genders_are_the_two_supported_values() -> None:
    assert set(constants.ALLOWED_GENDERS) == {"boy", "girl"}


@pytest.mark.parametrize(
    "name",
    ["LOG_EVENT_READ", "LOG_EVENT_UPSERT", "LOG_EVENT_UPSERT_FAILED"],
)
def test_log_events_are_dotted_amble_avatar_names(name: str) -> None:
    value = getattr(constants, name)
    assert isinstance(value, str)
    assert value.startswith("amble.avatar."), name


def test_error_message_is_user_safe_and_non_empty() -> None:
    assert constants.ERROR_MESSAGE_PERSISTENCE
    # Never leak internal detail (rule 10).
    assert "sql" not in constants.ERROR_MESSAGE_PERSISTENCE.lower()
    assert "traceback" not in constants.ERROR_MESSAGE_PERSISTENCE.lower()
