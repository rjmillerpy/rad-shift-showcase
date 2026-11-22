"""Tests for app/error_tracking/setup.py: the events Sentry would receive.

The network sender is replaced by one that keeps events in memory (the
external boundary); everything else is the real SDK on a small real app.
"""

import logging
from collections.abc import Iterator

import pytest
import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app.error_tracking.constants import DEFAULT_ENVIRONMENT, DEFAULT_TRACES_SAMPLE_RATE
from app.error_tracking.setup import (
    ErrorTrackingConfigError,
    configure_error_tracking,
    traces_sample_rate,
)
from app.logs.constants import REQUEST_ID_HEADER
from app.logs.middleware import RequestLogMiddleware

# Well-formed but never used: the transport below sends nothing.
FAKE_DSN = "https://public@example.invalid/1"
SENT: list[dict] = []


class _InMemoryTransport(Transport):
    def capture_envelope(self, envelope: Envelope) -> None:
        SENT.extend(item.payload.json for item in envelope.items if item.type == "event")


@pytest.fixture()
def sentry() -> Iterator[list[dict]]:
    SENT.clear()
    configure_error_tracking(
        FAKE_DSN, environment="test", release="abc1234", transport=_InMemoryTransport
    )
    yield SENT
    sentry_sdk.init()  # no DSN: the SDK is off again for every other test
    structlog.contextvars.clear_contextvars()


def _flush() -> list[dict]:
    sentry_sdk.flush()
    return SENT


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("handler failed")

    @app.get("/missing")
    def missing() -> None:
        raise HTTPException(status_code=404, detail="nope")

    @app.get("/logs-an-error")
    def logs_an_error() -> dict[str, str]:
        logging.getLogger("radshift.test").error("payment.provider.down")
        return {}

    app.add_middleware(RequestLogMiddleware)
    return app


@pytest.fixture()
def client(sentry) -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


class TestOff:
    @pytest.mark.parametrize("dsn", [None, ""])
    def test_without_a_dsn_nothing_starts(self, dsn):
        assert configure_error_tracking(dsn) is False
        assert not sentry_sdk.get_client().is_active()


class TestUnhandledExceptions:
    def test_become_events_with_environment_and_release(self, client):
        assert client.get("/boom").status_code == 500
        (event,) = _flush()
        (exception,) = event["exception"]["values"]
        assert (exception["type"], exception["value"]) == ("RuntimeError", "handler failed")
        assert (event["environment"], event["release"]) == ("test", "abc1234")

    def test_are_tagged_with_the_request_id_the_client_saw(self, client):
        response = client.get("/boom")
        (event,) = _flush()
        assert event["tags"]["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_carry_no_personal_data_or_tokens(self, client):
        client.get(
            "/boom",
            headers={
                "Cookie": "session=secret",
                "X-Forwarded-For": "203.0.113.9",
                "Authorization": "Bearer header.payload.signature",
            },
        )
        (event,) = _flush()
        # Anywhere in the event, stack frame variables included.
        for value in ("203.0.113.9", "session=secret", "header.payload.signature"):
            assert value not in str(event)
        assert "user" not in event or "ip_address" not in event["user"]


class TestTraceCorrelation:
    def test_an_event_inside_a_trace_is_tagged_with_its_trace_id(self, sentry):
        with TracerProvider().get_tracer("test").start_as_current_span("request") as span:
            sentry_sdk.capture_message("inside a trace")
        (event,) = _flush()
        assert event["tags"]["trace_id"] == format(span.get_span_context().trace_id, "032x")

    def test_outside_one_there_is_no_trace_tag(self, sentry):
        sentry_sdk.capture_message("no trace")
        (event,) = _flush()
        assert "trace_id" not in event.get("tags", {})


class TestWhatIsNotReported:
    def test_a_4xx_is_not_an_error(self, client):
        assert client.get("/missing").status_code == 404
        assert _flush() == []


class TestLoggedErrors:
    def test_an_error_log_becomes_an_event(self, client):
        client.get("/logs-an-error")
        (event,) = _flush()
        assert event["logentry"]["message"] == "payment.provider.down"
        assert "request_id" in event["tags"]

    def test_the_request_log_line_for_a_500_is_not_a_second_event(self, client):
        """The exception is the event; its ERROR access line would duplicate it."""
        client.get("/boom")
        assert len(_flush()) == 1


class TestDefaults:
    def test_environment_defaults_to_local(self, sentry):
        configure_error_tracking(FAKE_DSN, transport=_InMemoryTransport)
        assert sentry_sdk.get_client().options["environment"] == DEFAULT_ENVIRONMENT


class TestTracesSampleRate:
    @pytest.mark.parametrize("value", [None, ""])
    def test_unset_is_errors_only(self, value):
        assert traces_sample_rate(value) == DEFAULT_TRACES_SAMPLE_RATE == 0.0

    @pytest.mark.parametrize(("value", "rate"), [("0", 0.0), ("0.1", 0.1), ("1", 1.0)])
    def test_a_number_from_0_to_1(self, value, rate):
        assert traces_sample_rate(value) == rate

    @pytest.mark.parametrize("value", ["lots", "1.5", "-0.1"])
    def test_anything_else_is_refused(self, value):
        with pytest.raises(ErrorTrackingConfigError):
            traces_sample_rate(value)
