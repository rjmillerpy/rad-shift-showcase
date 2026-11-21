"""Process-wide logging: one JSON object per line, or readable lines in a terminal.

structlog formats every record, including those from plain
`logging.getLogger(__name__)` loggers, uvicorn and libraries, so existing
logging calls need no change. Fields passed as `extra={...}` become JSON keys
(the old text format dropped them), and whatever is bound to structlog's
context, such as the request id from app/logs/middleware.py, is added to every
line logged while that request is handled.
"""

import logging
import sys

import structlog
from structlog.types import Processor

from .constants import (
    CONSOLE_RENDERER,
    DEFAULT_LOG_LEVEL,
    JSON_RENDERER,
    QUIET_LOGGERS,
    UVICORN_ACCESS_LOGGER,
    UVICORN_LOGGERS,
)


class LogConfigError(ValueError):
    """LOG_RENDERER or LOG_LEVEL has a value logging can't use."""


# Run on every record, whichever API logged it.
_SHARED_PROCESSORS: tuple[Processor, ...] = (
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
)


def _renderer(name: str) -> list[Processor]:
    if name == JSON_RENDERER:
        # The traceback becomes one string field; JSON can't hold the object.
        return [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    if name == CONSOLE_RENDERER:
        # Prints the traceback itself, so it must get the raw exc_info.
        return [structlog.dev.ConsoleRenderer()]
    raise LogConfigError(
        f"log renderer must be {JSON_RENDERER!r} or {CONSOLE_RENDERER!r}, not {name!r}"
    )


def _level(name: str) -> int:
    level = logging.getLevelNamesMapping().get(name.upper())
    if level is None:
        raise LogConfigError(f"unknown log level {name!r}")
    return level


def configure_logging(renderer: str = JSON_RENDERER, level: str = DEFAULT_LOG_LEVEL) -> None:
    """Send every logger's records through structlog to stderr. Safe to call again."""
    # Both checked before anything changes, so a bad setting leaves logging as it was.
    render = _renderer(renderer)
    root_level = _level(level)
    formatter = structlog.stdlib.ProcessorFormatter(
        # For records from the standard library (most of the app, uvicorn,
        # libraries); ExtraAdder turns their `extra=` into fields.
        foreign_pre_chain=[*_SHARED_PROCESSORS, structlog.stdlib.ExtraAdder()],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *render,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(root_level)

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in (*UVICORN_LOGGERS, UVICORN_ACCESS_LOGGER):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    logging.getLogger(UVICORN_ACCESS_LOGGER).setLevel(logging.WARNING)

    # For code that logs through structlog's own API.
    structlog.configure(
        processors=[*_SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
