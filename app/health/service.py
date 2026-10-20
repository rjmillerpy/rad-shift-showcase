"""What "healthy" means: the checks behind the health endpoints."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .schema import HealthStatus, LivenessResponse, ReadinessChecks, ReadinessResponse

logger = logging.getLogger(__name__)

# The cheapest query that proves a round trip to the database works.
_DATABASE_PING = text("SELECT 1")


def liveness() -> LivenessResponse:
    """The process is up. Deliberately checks nothing else: an orchestrator
    restarts a container that fails liveness, and a restart can't fix a
    database outage."""
    return LivenessResponse(status=HealthStatus.OK)


def readiness(db: Session) -> ReadinessResponse:
    """Can this instance do real work? Today that means: the database answers."""
    database = _check_database(db)
    return ReadinessResponse(status=database, checks=ReadinessChecks(database=database))


def _check_database(db: Session) -> HealthStatus:
    try:
        db.execute(_DATABASE_PING)
    except SQLAlchemyError:
        # The detail (host, user, driver message) goes to the log only: the
        # endpoint is unauthenticated, so the response just says "unavailable".
        logger.exception("Health check: database ping failed")
        return HealthStatus.UNAVAILABLE
    return HealthStatus.OK
