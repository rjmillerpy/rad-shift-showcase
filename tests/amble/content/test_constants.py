"""Tests for app/amble/content/constants.py — invariants other modules rely on."""

import time

from app.amble.content import constants


class TestBindingsConfig:
    def test_demo_bindings_ship_with_the_module(self):
        assert constants.DEMO_BINDINGS_PATH.is_file()


class TestPageLimits:
    def test_default_is_within_the_maximum(self):
        assert 1 <= constants.DEFAULT_PAGE_LIMIT <= constants.MAX_PAGE_LIMIT


class TestRanking:
    def test_follow_boost_outranks_any_real_timestamp(self):
        """The boost is added to a unix timestamp; it only works as a tier
        if it is larger than every timestamp it could be compared with."""
        a_century_from_now = int(time.time()) + 100 * 365 * 24 * 60 * 60
        assert a_century_from_now < constants.FOLLOW_BOOST_RANK

    def test_stale_threshold_is_a_positive_number_of_days(self):
        one_day = 60 * 60 * 24
        assert one_day <= constants.FRESHNESS_STALE_SECONDS
        assert constants.FRESHNESS_STALE_SECONDS % one_day == 0


class TestMessages:
    def test_log_event_names_are_distinct(self):
        events = [
            constants.LOG_EVENT_FETCH,
            constants.LOG_EVENT_FETCH_UNKNOWN_ENTITY,
            constants.LOG_EVENT_BINDINGS_LOADED,
            constants.LOG_EVENT_BINDINGS_ERROR,
        ]
        assert len(set(events)) == len(events)

    def test_error_messages_are_distinct_and_non_empty(self):
        assert constants.ERROR_MESSAGE_UNKNOWN_ENTITY
        assert constants.ERROR_MESSAGE_BAD_CURSOR
        assert constants.ERROR_MESSAGE_UNKNOWN_ENTITY != constants.ERROR_MESSAGE_BAD_CURSOR
