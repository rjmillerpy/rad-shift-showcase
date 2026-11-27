"""The reader's feed mode and client, carried from the request to where engagements are recorded.

Engagements are recorded deep in app/posts/toggles.py, far from the request;
this middleware puts what they need in a context variable on the way in.
FastAPI runs sync endpoints in a worker thread with a copy of the context,
so the value set here is visible there.
"""

from contextvars import ContextVar

from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from app.posts.models import PostModel

from .constants import FEED_MODE_HEADER, FEED_MODES
from .service import Client, record_engagement

_request: ContextVar[tuple[str | None, Client] | None] = ContextVar(
    "analytics_request", default=None
)


def current() -> tuple[str | None, Client] | None:
    """(feed mode or None, client) for the request being handled, or None outside one."""
    return _request.get()


def record_engagement_here(action: str, post: PostModel, db: Session) -> None:
    """Record an engagement made in the current request; nothing outside a request."""
    request = current()
    if request is not None:
        mode, client = request
        record_engagement(action, post, mode, client, db)


class AnalyticsContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {
                name.decode("latin-1"): value.decode("latin-1") for name, value in scope["headers"]
            }
            mode = headers.get(FEED_MODE_HEADER)
            client = Client(
                ip=(scope.get("client") or ("", 0))[0],
                user_agent=headers.get("user-agent", ""),
            )
            _request.set((mode if mode in FEED_MODES else None, client))
        await self._app(scope, receive, send)
