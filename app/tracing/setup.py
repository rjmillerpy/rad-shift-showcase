"""Distributed tracing with OpenTelemetry (roadmap item 26).

Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (tests, CI and the plain dev
stack); the observability overlay's Tempo receives the spans when it is on
(compose.observability.yaml). Each request becomes a trace: a server span
from the FastAPI instrumentation, a child span per SQL statement and per
outgoing httpx call. A caller's `traceparent` header is continued, so a
trace started elsewhere carries on through this service.

The provider is passed to each instrumentation instead of being installed
globally, so building the app more than once (as the tests do) never meets
OpenTelemetry's set-only-once global.
"""

import logging

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from sqlalchemy import Engine

from .constants import (
    DEFAULT_SERVICE_NAME,
    EXCLUDED_URLS,
    EXPORT_TIMEOUT_SECONDS,
    TRACES_PATH,
)

logger = logging.getLogger(__name__)


def tracer_provider(
    endpoint: str | None,
    service_name: str | None = None,
    exporter: SpanExporter | None = None,
) -> TracerProvider | None:
    """A provider exporting to `endpoint` over OTLP/HTTP, or None when tracing is off.

    `exporter` replaces the network exporter (tests keep spans in memory).
    """
    if not endpoint and exporter is None:
        return None
    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: service_name or DEFAULT_SERVICE_NAME})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            exporter
            or OTLPSpanExporter(
                endpoint=f"{(endpoint or '').rstrip('/')}{TRACES_PATH}",
                timeout=EXPORT_TIMEOUT_SECONDS,
            )
        )
    )
    return provider


def instrument(app: FastAPI, engine: Engine, provider: TracerProvider | None) -> None:
    """Trace the app's requests, its SQL and its outgoing HTTP calls (no-op when off)."""
    if provider is None:
        logger.info("Tracing off (no OTEL_EXPORTER_OTLP_ENDPOINT)")
        return
    # Added last, so it wraps every other middleware: the request log line
    # and Sentry events are written inside the request's span.
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=EXCLUDED_URLS)
    # 0.66b2 (newest) declares sqlalchemy < 2.1 and otherwise does nothing on
    # 2.1.x; the hooks it uses are unchanged, and the tests check SQL spans
    # appear. Drop skip_dep_check once a release declares 2.1.
    SQLAlchemyInstrumentor().instrument(
        engine=engine, tracer_provider=provider, skip_dep_check=True
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    logger.info("Tracing on")
