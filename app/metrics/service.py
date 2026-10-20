"""Request metrics in Prometheus' text format: what is recorded and how it is rendered.

Two series families, the minimum a dashboard and an error-rate alert need:

  http_requests_total{method, route, status}         counter
  http_request_duration_seconds{method, route}       histogram

`route` is the route template ("/posts/{post_id}"), never the raw path:
one label value per real path would create a new time series for every
post id and every scanner probe, which is how a Prometheus runs out of
memory. Paths that match no route share one value, UNMATCHED_ROUTE.

The process collector that prometheus_client registers by default adds
CPU, memory and open file descriptors for free.

METRICS_ENABLED=false removes the endpoint and the middleware. ECS sets it
(infra/ecs.tf): nothing scrapes the app on AWS, where CloudWatch reads the
load balancer's metrics instead, and a route that doesn't exist can't be
reached by any path trick a proxy rule might miss.
"""

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

METRICS_ENABLED_ENV_VAR = "METRICS_ENABLED"

# Where the scrape endpoint lives. Internal only: the proxy (caddy/Caddyfile)
# and the load balancer (infra/alb.tf) refuse it from outside.
METRICS_PATH = "/metrics"

# The label value for any request no route matched (404s, scanner probes).
UNMATCHED_ROUTE = "<unmatched>"

# The media type Prometheus expects from a scrape.
METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST

# Latency buckets in seconds: fine-grained where this API usually answers
# (a few ms to a few hundred), coarse beyond. p95 is estimated from these.
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class RequestMetrics:
    """The request counter and latency histogram, registered on one registry."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._registry = registry
        # prometheus_client appends _total to a counter's name on export.
        self._requests = Counter(
            "http_requests",
            "HTTP requests handled, by method, route template and status code.",
            ["method", "route", "status"],
            registry=registry,
        )
        self._duration = Histogram(
            "http_request_duration_seconds",
            "Time from receiving a request to the end of the handler, in seconds.",
            ["method", "route"],
            buckets=LATENCY_BUCKETS,
            registry=registry,
        )

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        self._requests.labels(method=method, route=route, status=str(status)).inc()
        self._duration.labels(method=method, route=route).observe(seconds)

    def render(self) -> bytes:
        """Everything on the registry, in the text exposition format."""
        return generate_latest(self._registry)


# One instance per process: a metric can be registered only once per registry,
# and create_app() runs more than once in the tests.
REQUEST_METRICS = RequestMetrics(REGISTRY)


def metrics_enabled() -> bool:
    """On unless METRICS_ENABLED is "false" (any case)."""
    return os.getenv(METRICS_ENABLED_ENV_VAR, "true").lower() != "false"
