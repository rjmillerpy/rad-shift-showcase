"""The app-wide dependency that applies the rate-limit policies to every request."""

import logging
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.common.auth_jwt import AuthJWT, AuthJWTException
from app.common.db import get_db
from app.ratelimit.constants import ROUTE_POLICIES, WRITE, WRITE_METHODS, Policy
from app.ratelimit.service import hit, rate_limits_enabled

logger = logging.getLogger(__name__)

LOG_EVENT_LIMITED = "ratelimit.limited"


def policy_for(method: str, route: str) -> Policy | None:
    """The policy a request falls under, or None for an unlimited read."""
    policy = ROUTE_POLICIES.get((method, route))
    if policy is None and method in WRITE_METHODS:
        return WRITE
    return policy


def identity_for(request: Request, policy: Policy) -> str:
    """Who is counted: the signed-in user where the policy says so, else the IP.

    The token is only read here, not required: a bad one just means the IP
    is counted, and the endpoint itself still refuses it as usual.
    """
    if policy.per_user:
        jwt = AuthJWT(request)
        try:
            jwt.jwt_optional()
            username = jwt.get_jwt_subject()
        except AuthJWTException:
            username = None
        if username:
            return f"user:{username}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def enforce_rate_limits(request: Request, db: Session = Depends(get_db)) -> None:
    """429 with Retry-After once a client is over its policy's limit."""
    if not rate_limits_enabled():
        return
    # The full template ("/auth/login"): the matched route's own .path is
    # relative to its router's prefix ("/login").
    route = request.app.state.route_templates.of(request.scope)
    policy = policy_for(request.method, route)
    if policy is None:
        return
    decision = hit(db, policy, identity_for(request, policy), int(time.time()))
    if not decision.allowed:
        logger.warning(LOG_EVENT_LIMITED, extra={"policy": policy.name, "route": route})
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests: try again in {decision.retry_after} s",
            headers={"Retry-After": str(decision.retry_after)},
        )
