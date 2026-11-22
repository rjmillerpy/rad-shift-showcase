"""Fixtures for tests of app/tracing/: a real provider whose spans stay in memory."""

from collections.abc import Iterator

import pytest
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.tracing.setup import tracer_provider


@pytest.fixture()
def spans() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture()
def provider(spans) -> Iterator[TracerProvider]:
    built = tracer_provider(None, exporter=spans)
    assert built is not None
    yield built
    # The SQLAlchemy and httpx instrumentations patch process-wide.
    for instrumentor in (SQLAlchemyInstrumentor(), HTTPXClientInstrumentor()):
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
    built.shutdown()


def finished(provider: TracerProvider, spans: InMemorySpanExporter) -> list:
    provider.force_flush()
    return list(spans.get_finished_spans())
