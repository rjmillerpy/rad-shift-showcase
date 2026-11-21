"""Fixtures for tests of app/logs/: real logging output, with global state put back."""

import io
import json
import logging
from collections.abc import Callable, Iterator

import pytest
import structlog

from app.logs.constants import QUIET_LOGGERS, UVICORN_ACCESS_LOGGER, UVICORN_LOGGERS
from app.logs.setup import configure_logging

_TOUCHED_LOGGERS = ("", *QUIET_LOGGERS, *UVICORN_LOGGERS, UVICORN_ACCESS_LOGGER)


@pytest.fixture()
def restore_logging() -> Iterator[None]:
    """configure_logging changes process-wide state; undo it after the test."""
    saved = {
        name: (logger.handlers[:], logger.level, logger.propagate)
        for name in _TOUCHED_LOGGERS
        for logger in [logging.getLogger(name)]
    }
    saved_structlog = structlog.get_config()
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers, logger.level, logger.propagate = handlers, level, propagate
    structlog.configure(**saved_structlog)
    structlog.contextvars.clear_contextvars()


@pytest.fixture()
def configure_logging_into_buffer(restore_logging) -> Callable[..., io.StringIO]:
    """configure_logging, with the handler writing to a buffer the test reads.

    Not pytest's captured stderr: pytest swaps that stream between a fixture's
    setup and the test body, so a handler made here would write to a closed one.
    """

    def _configure(*args: str) -> io.StringIO:
        configure_logging(*args)
        buffer = io.StringIO()
        (handler,) = logging.getLogger().handlers
        assert isinstance(handler, logging.StreamHandler)
        handler.setStream(buffer)
        return buffer

    return _configure


@pytest.fixture()
def json_logs(configure_logging_into_buffer) -> Callable[[], list[dict]]:
    """Logging configured as in production; returns a reader for the lines written since."""
    buffer = configure_logging_into_buffer()

    def _read() -> list[dict]:
        lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
        buffer.seek(0)
        buffer.truncate()
        return lines

    return _read
