"""The current trace and span ids, for log lines and Sentry events.

Read from OpenTelemetry's context, so they are set only while a request is
being traced; outside one (startup, tracing off) there is nothing to add.
"""

from opentelemetry import trace

from .constants import SPAN_ID_KEY, TRACE_ID_KEY


def current_trace_ids() -> dict[str, str]:
    """{"trace_id": 32 hex, "span_id": 16 hex} inside a traced request, else {}."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {
        TRACE_ID_KEY: format(context.trace_id, "032x"),
        SPAN_ID_KEY: format(context.span_id, "016x"),
    }
