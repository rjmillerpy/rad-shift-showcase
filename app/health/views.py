"""Health endpoints for load balancers, orchestrators and Docker healthchecks.

GET /health/live  liveness: the process is up and serving requests.
GET /health       readiness: the app can do real work (the database answers).
                  503 tells a load balancer to stop sending traffic here.

Both are unauthenticated and uncached. What each one checks lives in
service.py; this module only maps the result onto HTTP.
"""

from http import HTTPStatus

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.common.db import get_db

from . import service
from .schema import HealthStatus, LivenessResponse, ReadinessResponse

health_router = APIRouter()

# Health responses describe this instant; nothing in between may cache them.
_CACHE_CONTROL_HEADER = "Cache-Control"
_NO_STORE = "no-store"


@health_router.get("/live")
def live(response: Response) -> LivenessResponse:
    response.headers[_CACHE_CONTROL_HEADER] = _NO_STORE
    return service.liveness()


@health_router.get("")
def ready(response: Response, db: Session = Depends(get_db)) -> ReadinessResponse:
    response.headers[_CACHE_CONTROL_HEADER] = _NO_STORE
    result = service.readiness(db)
    if result.status is not HealthStatus.OK:
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
    return result
