"""Tests for app/generators/constants.py — enums + numeric tunables."""

from app.generators import constants


class TestRunStatus:
    def test_values(self):
        assert {s.value for s in constants.RunStatus} == {"running", "success", "failed"}

    def test_str_enum_equality(self):
        assert constants.RunStatus.RUNNING == "running"
        assert constants.RunStatus.SUCCESS == "success"
        assert constants.RunStatus.FAILED == "failed"


class TestFailureHandling:
    def test_max_consecutive_failures_positive(self):
        assert constants.MAX_CONSECUTIVE_FAILURES > 0

    def test_max_error_message_bounded(self):
        assert 0 < constants.MAX_ERROR_MESSAGE_CHARS <= 10_000

    def test_status_codes_reasonable(self):
        assert constants.FETCH_FAILURE_STATUS == 502
        assert constants.GENERIC_FAILURE_STATUS == 500


class TestAnalyzer:
    def test_max_tokens_positive(self):
        assert constants.ANALYZER_MAX_TOKENS > 0

    def test_timeout_bounded(self):
        assert 1 <= constants.ANALYZER_API_TIMEOUT_SECONDS <= 120


class TestScheduler:
    def test_poll_interval_positive(self):
        assert constants.SCHEDULER_POLL_INTERVAL_SECONDS > 0

    def test_max_sources_per_tick_bounded(self):
        assert 1 <= constants.SCHEDULER_MAX_SOURCES_PER_TICK <= 100

    def test_join_timeout_bounded(self):
        assert 1 <= constants.SCHEDULER_JOIN_TIMEOUT_SECONDS <= 60


class TestListBounds:
    def test_list_bounds_ordered(self):
        assert constants.DEFAULT_LIST_LIMIT <= constants.MAX_LIST_LIMIT

    def test_run_bounds_ordered(self):
        assert constants.DEFAULT_RUN_LIMIT <= constants.MAX_RUN_LIMIT
