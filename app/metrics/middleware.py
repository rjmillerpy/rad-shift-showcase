"""ASGI middleware that times every HTTP request and records it in REQUEST_METRICS.

Plain ASGI rather than Starlette's BaseHTTPMiddleware, which buffers
streaming responses (the chronicle stream is server-sent events).
"""

import time
from collections.abc import Sequence
from http import HTTPStatus

from fastapi.routing import iter_route_contexts
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .service import METRICS_PATH, UNMATCHED_ROUTE, RequestMetrics


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: RequestMetrics) -> None:
        self._app = app
        self._metrics = metrics
        # id(route) -> full path template. Built on the first request,
        # because routers are included after the middleware is added.
        self._templates: dict[int, str] | None = None

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
            route = self._route_template(scope)
            # Scrapes every few seconds would drown out real traffic.
            if route != METRICS_PATH:
                self._metrics.observe(scope["method"], route, status, time.perf_counter() - started)

    def _route_template(self, scope: Scope) -> str:
        """The matched route's full path template ("/health/live").

        The router stores the matched route in the scope it was handed,
        which is this same dict. That route's own .path is relative to its
        router's prefix ("/live"), so the full template comes from FastAPI's
        flattened route list.
        """
        route = scope.get("route")
        if route is None:
            return UNMATCHED_ROUTE
        if self._templates is None:
            self._templates = _full_templates(scope["app"].routes)
        return self._templates.get(id(route), UNMATCHED_ROUTE)


def _full_templates(routes: Sequence[BaseRoute]) -> dict[int, str]:
    # Keyed by id(): Starlette routes define __eq__ without __hash__.
    return {
        id(context.original_route): context.path
        for context in iter_route_contexts(routes)
        if context.path is not None
    }
