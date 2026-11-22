"""Settings and names for distributed tracing with OpenTelemetry (roadmap item 26)."""

# The standard OpenTelemetry variables, so any OTLP backend works unchanged
# (Tempo here; Grafana Cloud, Honeycomb or a collector elsewhere).
OTLP_ENDPOINT_ENV_VAR = "OTEL_EXPORTER_OTLP_ENDPOINT"
SERVICE_NAME_ENV_VAR = "OTEL_SERVICE_NAME"

DEFAULT_SERVICE_NAME = "rad-shift-backend"
# OTLP over HTTP appends this to the base endpoint.
TRACES_PATH = "/v1/traces"
# An export that can't reach the collector gives up instead of holding spans.
EXPORT_TIMEOUT_SECONDS = 5

# Hit every few seconds; a trace for each would bury real traffic (the same
# routes the request log keeps at DEBUG). A comma-separated regex list.
EXCLUDED_URLS = "/health,/metrics"

# Field and tag names that carry the ids into logs and Sentry events.
TRACE_ID_KEY = "trace_id"
SPAN_ID_KEY = "span_id"
