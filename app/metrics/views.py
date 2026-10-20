"""GET /metrics: the scrape endpoint for Prometheus.

Text, not JSON, so it has no response model (rule 46 covers JSON
endpoints); left out of the OpenAPI docs because it is not part of the
public API. Unauthenticated like a health check, and kept internal by the
proxy and the load balancer instead.
"""

from fastapi import APIRouter, Response

from .service import METRICS_CONTENT_TYPE, REQUEST_METRICS

metrics_router = APIRouter()


@metrics_router.get("", include_in_schema=False)
def metrics() -> Response:
    return Response(REQUEST_METRICS.render(), media_type=METRICS_CONTENT_TYPE)
