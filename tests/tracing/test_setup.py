"""Tests for app/tracing/setup.py, on a small real app, a real SQLite engine
and spans kept in memory (the exporter is the external boundary)."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.resources import SERVICE_NAME
from opentelemetry.trace import SpanKind
from sqlalchemy import create_engine, text

from app.logs.middleware import RequestLogMiddleware
from app.tracing.constants import DEFAULT_SERVICE_NAME, TRACES_PATH
from app.tracing.context import current_trace_ids
from app.tracing.setup import instrument, tracer_provider

from .conftest import finished

# W3C trace context a caller (a proxy, the frontend) would send.
CALLER_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{CALLER_TRACE_ID}-00f067aa0ba902b7-01"


class _NoContent(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - the stdlib's handler name
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def upstream() -> Iterator[str]:
    """A real HTTP server on localhost, standing in for an external API."""
    server = HTTPServer(("127.0.0.1", 0), _NoContent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/thing"
    server.shutdown()
    server.server_close()


class _Collector(BaseHTTPRequestHandler):
    received: list[tuple[str, str]] = []

    def do_POST(self) -> None:  # noqa: N802 - the stdlib's handler name
        self.rfile.read(int(self.headers["Content-Length"]))
        _Collector.received.append((self.path, self.headers["Content-Type"]))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture()
def collector() -> Iterator[tuple[str, list[tuple[str, str]]]]:
    """A local stand-in for Tempo's OTLP/HTTP receiver, recording each export."""
    _Collector.received = []
    server = HTTPServer(("127.0.0.1", 0), _Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", _Collector.received
    server.shutdown()
    server.server_close()


def _app(provider, upstream_url: str = "") -> tuple[FastAPI, list[dict[str, str]]]:
    engine = create_engine("sqlite://")
    seen: list[dict[str, str]] = []
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        seen.append(current_trace_ids())
        return {"id": item_id}

    @app.get("/calls-out")
    def calls_out() -> dict[str, str]:
        httpx.get(upstream_url, timeout=5)
        return {}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {}

    app.add_middleware(RequestLogMiddleware)
    instrument(app, engine, provider)
    return app, seen


class TestOff:
    def test_no_endpoint_no_provider(self):
        assert tracer_provider(None) is None
        assert tracer_provider("") is None

    def test_instrumenting_with_no_provider_changes_nothing(self):
        app, seen = _app(None)
        TestClient(app).get("/items/1")
        assert seen == [{}]


class TestOn:
    def test_exports_over_otlp_http_to_the_traces_path(self, collector):
        base_url, received = collector
        provider = tracer_provider(base_url + "/")
        assert provider is not None
        with provider.get_tracer("test").start_as_current_span("work"):
            pass
        provider.force_flush()
        provider.shutdown()
        assert received == [(TRACES_PATH, "application/x-protobuf")]

    def test_spans_name_the_service(self, provider):
        assert provider.resource.attributes[SERVICE_NAME] == DEFAULT_SERVICE_NAME

    def test_a_service_name_can_be_set(self, spans):
        provider = tracer_provider(None, "rad-shift-worker", exporter=spans)
        assert provider is not None
        assert provider.resource.attributes[SERVICE_NAME] == "rad-shift-worker"
        provider.shutdown()


class TestRequests:
    def test_a_request_is_a_server_span_named_by_route_template(self, provider, spans):
        app, _ = _app(provider)
        TestClient(app).get("/items/42")
        server = [s for s in finished(provider, spans) if s.kind is SpanKind.SERVER]
        (span,) = server
        assert span.name == "GET /items/{item_id}"
        assert span.attributes["http.route"] == "/items/{item_id}"

    def test_sql_is_a_child_span_of_the_request(self, provider, spans):
        app, _ = _app(provider)
        TestClient(app).get("/items/1")
        done = finished(provider, spans)
        (server,) = [s for s in done if s.kind is SpanKind.SERVER]
        (sql,) = [s for s in done if s.kind is SpanKind.CLIENT and "SELECT" in s.name]
        assert sql.context.trace_id == server.context.trace_id

    def test_an_outgoing_http_call_is_a_child_span(self, provider, spans, upstream):
        app, _ = _app(provider, upstream)
        TestClient(app).get("/calls-out")
        done = finished(provider, spans)
        (server,) = [s for s in done if s.kind is SpanKind.SERVER]
        (call,) = [s for s in done if s.kind is SpanKind.CLIENT and s.name.startswith("GET")]
        assert call.context.trace_id == server.context.trace_id

    def test_a_callers_traceparent_is_continued(self, provider, spans):
        app, seen = _app(provider)
        TestClient(app).get("/items/1", headers={"traceparent": TRACEPARENT})
        (server,) = [s for s in finished(provider, spans) if s.kind is SpanKind.SERVER]
        assert format(server.context.trace_id, "032x") == CALLER_TRACE_ID
        assert seen[0]["trace_id"] == CALLER_TRACE_ID

    def test_health_checks_are_not_traced(self, provider, spans):
        app, _ = _app(provider)
        TestClient(app).get("/health")
        assert [s for s in finished(provider, spans) if s.kind is SpanKind.SERVER] == []


class TestCorrelation:
    def test_handler_code_sees_the_requests_trace(self, provider, spans):
        app, seen = _app(provider)
        TestClient(app).get("/items/1")
        (server,) = [s for s in finished(provider, spans) if s.kind is SpanKind.SERVER]
        assert seen[0]["trace_id"] == format(server.context.trace_id, "032x")


@pytest.fixture(autouse=True)
def _no_leftover_spans(spans):
    yield
    spans.clear()
