"""ASGI middleware that times every HTTP request and records it in REQUEST_METRICS.

Plain ASGI rather than Starlette's BaseHTTPMiddleware, which buffers
streaming responses (the chronicle stream is server-sent events).
"""

import time
from http import HTTPStatus

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.route_templates import RouteTemplates

from .service import METRICS_PATH, RequestMetrics


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: RequestMetrics) -> None:
        self._app = app
        self._metrics = metrics
        self._routes = RouteTemplates()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # An exception that escapes before a response starts becomes a 500
        # in Starlette's outermost error handler, outside this middleware.
        status = HTTPStatus.INTERNAL_SERVER_ERROR.value
        started = time.perf_counter()

        async def send_and_capture_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, send_and_capture_status)
        finally:
            route = self._routes.of(scope)
            # Scrapes every few seconds would drown out real traffic.
            if route != METRICS_PATH:
                self._metrics.observe(scope["method"], route, status, time.perf_counter() - started)
