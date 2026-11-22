"""Tests for app/tracing/context.py."""

from opentelemetry.sdk.trace import TracerProvider

from app.tracing.constants import SPAN_ID_KEY, TRACE_ID_KEY
from app.tracing.context import current_trace_ids


def test_nothing_outside_a_span():
    assert current_trace_ids() == {}


def test_the_current_span_ids_as_hex():
    with TracerProvider().get_tracer("test").start_as_current_span("work") as span:
        ids = current_trace_ids()
        context = span.get_span_context()
    assert ids == {
        TRACE_ID_KEY: format(context.trace_id, "032x"),
        SPAN_ID_KEY: format(context.span_id, "016x"),
    }
    assert len(ids[TRACE_ID_KEY]) == 32 and len(ids[SPAN_ID_KEY]) == 16
