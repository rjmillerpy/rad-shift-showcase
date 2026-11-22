"""Tests for app/error_tracking/constants.py."""

import logging

from app.error_tracking.constants import IGNORED_LOGGERS
from app.logs import middleware


def test_the_request_log_logger_is_the_one_ignored():
    """Renaming the middleware's logger would quietly double every 5xx in Sentry."""
    assert middleware.logger.name in IGNORED_LOGGERS
    assert all(isinstance(logging.getLogger(name), logging.Logger) for name in IGNORED_LOGGERS)
