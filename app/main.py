"""FastAPI app factory: lifespan, CORS, metrics, JWT error handling, router registration."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.auth_jwt import AuthJWTException

from .amble.avatar.views import amble_avatar_router
from .amble.content import bindings as amble_bindings
from .amble.content.views import amble_content_router
from .auth.views import auth_router
from .avatar.views import avatar_router
from .blog.views import blog_router
from .common.config import Config
from .common.db import create_tables
from .flags import service as flags
from .follow.views import follow_router
from .generators.scheduler import start_scheduler, stop_scheduler
from .generators.views import generator_router
from .health.views import health_router
from .metrics.middleware import MetricsMiddleware
from .metrics.service import METRICS_PATH, REQUEST_METRICS, metrics_enabled
from .metrics.views import metrics_router
from .plugins import edition
from .posts.views import posts_router
from .profile.views import profile_router
from .trends.views import trends_router
from .widgets.views import widget_router

logger = logging.getLogger(__name__)

# Sent when an auth error carries no message of its own.
DEFAULT_AUTH_ERROR_DETAIL = "Invalid or expired token"


# (router, prefix) pairs — one row per domain. Adding a new domain is a one-line change.
# The edition (app/plugins.py) adds its own after these.
_ROUTERS: list[tuple] = [
    (auth_router, "/auth"),
    (profile_router, "/profile"),
    (posts_router, "/posts"),
    (follow_router, "/follow"),
    (blog_router, "/blog"),
    (avatar_router, "/avatar"),
    (amble_avatar_router, "/amble/avatar"),
    (amble_content_router, "/amble/content"),
    (widget_router, "/widgets"),
    (generator_router, "/generators"),
    (trends_router, "/trends"),
    (health_router, "/health"),
]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    flags.configure()
    start_scheduler()
    logger.info("Generator scheduler started")
    try:
        yield
    finally:
        stop_scheduler()
        logger.info("Generator scheduler stopped")
        flags.shutdown()


def _authjwt_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Turn a JWT error into a JSON response.

    app.common.auth_jwt decides the status and the client-safe message
    (401 for a missing or expired token, which is what sends the frontend
    to the login page; 422 for an invalid one). This only renders them.
    """
    if not isinstance(exc, AuthJWTException):  # registered only for AuthJWTException
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message or DEFAULT_AUTH_ERROR_DETAIL},
    )


def create_app() -> FastAPI:
    app = FastAPI(lifespan=_lifespan)

    app.add_exception_handler(AuthJWTException, _authjwt_exception_handler)

    # Starlette runs the last-added middleware first (outermost).
    if metrics_enabled():
        # Wraps the app and times every request that reaches it; CORS
        # preflights are answered outside it, by CORSMiddleware.
        app.add_middleware(MetricsMiddleware, metrics=REQUEST_METRICS)
        app.include_router(metrics_router, prefix=METRICS_PATH)
        logger.info("Request metrics enabled at %s", METRICS_PATH)
    # Added last, so it is outermost: every response, including an error
    # raised by any other middleware, carries the CORS headers. Inside
    # another middleware, that middleware's failures would reach the browser
    # as a misleading CORS error.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Config.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    create_tables()
    logger.info("Database tables ensured")
    amble_bindings.preload()

    routers = [*_ROUTERS, *edition().routers]
    for router, prefix in routers:
        app.include_router(router, prefix=prefix)
    logger.info("Registered %d routers", len(routers))

    return app


app = create_app()
