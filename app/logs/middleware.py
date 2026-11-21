"""ASGI middleware that gives every HTTP request an id and writes one log line for it.

The id is the caller's X-Request-ID when it looks like an id (a proxy or the
frontend may have started the trace), otherwise a new UUID. It is bound to
structlog's context, so every line logged while the request is handled
carries it, and it is returned in the X-Request-ID response header, so a
user's bug report leads straight to the server's lines.

Plain ASGI rather than Starlette's BaseHTTPMiddleware, which buffers
streaming responses (the chronicle stream is server-sent events).
"""

import logging
import time
import uuid
from http import HTTPStatus

import structlog
from starlette.datastructures import MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.route_templates import RouteTemplates

from .constants import (
    LOG_EVENT_REQUEST,
    QUIET_LEVEL,
    QUIET_ROUTES,
    REQUEST_ID_HEADER,
    REQUEST_ID_PATTERN,
    SERVER_ERROR_LEVEL,
)

logger = logging.getLogger(__name__)

# Where AuthJWT (app/common/auth_jwt.py) leaves a verified token's username.
USER_STATE_KEY = "user"


class RequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._routes = RouteTemplates()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _request_id(scope)
        # Each request runs in its own task, so this context is the
        # request's alone; clearing first guards against reuse anyway.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        status: int | None = None
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_id)
        except Exception:
            # Answer here, so the 500 carries the request id (and, from
            # CORSMiddleware outside, CORS headers); Starlette's outermost
            # handler only answers when no response has started. Re-raised
            # so uvicorn logs the traceback, still inside this context.
            if status is None:
                await _server_error(scope, receive, send_with_id)
            raise
        finally:
            self._log(scope, status, time.perf_counter() - started)

    def _log(self, scope: Scope, status: int | None, seconds: float) -> None:
        route = self._routes.of(scope)
        final_status = status or HTTPStatus.INTERNAL_SERVER_ERROR.value
        if final_status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            level = SERVER_ERROR_LEVEL
        elif route in QUIET_ROUTES:
            level = QUIET_LEVEL
        else:
            level = logging.INFO
        logger.log(
            level,
            LOG_EVENT_REQUEST,
            extra={
                "method": scope["method"],
                "route": route,
                "status": final_status,
                "duration_ms": round(seconds * 1000, 1),
                USER_STATE_KEY: scope.get("state", {}).get(USER_STATE_KEY),
            },
        )


def _request_id(scope: Scope) -> str:
    header = REQUEST_ID_HEADER.encode()
    for name, value in scope["headers"]:
        if name == header:
            candidate = value.decode("latin-1")
            if REQUEST_ID_PATTERN.fullmatch(candidate):
                return candidate
            break
    return uuid.uuid4().hex


async def _server_error(scope: Scope, receive: Receive, send: Send) -> None:
    # The same body Starlette's own handler sends.
    response = PlainTextResponse(
        HTTPStatus.INTERNAL_SERVER_ERROR.phrase, status_code=HTTPStatus.INTERNAL_SERVER_ERROR
    )
    await response(scope, receive, send)
