"""Error tracking with Sentry (roadmap item 25).

Off unless SENTRY_DSN is set, so tests, CI and e2e never send anything.
When on, the SDK's FastAPI integration reports unhandled exceptions and 5xx
HTTPExceptions, and records logged at ERROR become events too. Each event
is tagged with the request id (app/logs/middleware.py), so an issue in
Sentry leads to the same request's lines in Loki. No personal data is sent:
no IP addresses, cookies, tokens or request bodies, and no stack frame
variables (they hold the raw headers).
"""

import logging

import sentry_sdk
import structlog
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.transport import Transport
from sentry_sdk.types import Event, Hint

from .constants import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_TRACES_SAMPLE_RATE,
    IGNORED_LOGGERS,
    REQUEST_ID_TAG,
)

logger = logging.getLogger(__name__)


class ErrorTrackingConfigError(ValueError):
    """SENTRY_TRACES_SAMPLE_RATE isn't a number from 0 to 1."""


def traces_sample_rate(value: str | None) -> float:
    """Parse SENTRY_TRACES_SAMPLE_RATE (unset or empty: the default)."""
    if not value:
        return DEFAULT_TRACES_SAMPLE_RATE
    try:
        rate = float(value)
    except ValueError as err:
        raise ErrorTrackingConfigError(
            f"traces sample rate must be a number, not {value!r}"
        ) from err
    if not 0.0 <= rate <= 1.0:
        raise ErrorTrackingConfigError(f"traces sample rate must be from 0 to 1, not {rate}")
    return rate


def _tag_request_id(event: Event, hint: Hint) -> Event:
    request_id = structlog.contextvars.get_contextvars().get(REQUEST_ID_TAG)
    if request_id is not None:
        event.setdefault("tags", {})[REQUEST_ID_TAG] = request_id
    return event


def configure_error_tracking(
    dsn: str | None,
    environment: str | None = None,
    release: str | None = None,
    sample_rate: float = DEFAULT_TRACES_SAMPLE_RATE,
    transport: type[Transport] | None = None,
) -> bool:
    """Start the Sentry SDK if a DSN is set; returns whether it is on.

    With no `release`, the SDK reads SENTRY_RELEASE (set in the image).
    `transport` replaces the network sender (tests capture events with it).
    """
    if not dsn:
        logger.info("Error tracking off (no SENTRY_DSN)")
        return False
    for name in IGNORED_LOGGERS:
        ignore_logger(name)
    sentry_sdk.init(
        dsn=dsn,
        environment=environment or DEFAULT_ENVIRONMENT,
        release=release or None,
        traces_sample_rate=sample_rate,
        # No send_default_pii (deprecated in 2.74): left unset, the SDK
        # sends no user info, cookies or bodies in the request it reports.
        # Stack frames' local variables are a separate path: they hold the
        # raw ASGI headers (Authorization tokens, cookies, client IPs) and
        # are sent unfiltered, so they stay off.
        include_local_variables=False,
        before_send=_tag_request_id,
        transport=transport,
    )
    logger.info("Error tracking on", extra={"environment": environment or DEFAULT_ENVIRONMENT})
    return True
