"""The matched route's full path template ("/posts/{post_id}"), never the raw path.

Metrics label requests by it (a fixed set of values, however many ids there
are), and the request log records it so one query finds every call to an
endpoint.
"""

from collections.abc import Sequence

from fastapi.routing import iter_route_contexts
from starlette.routing import BaseRoute
from starlette.types import Scope

# Shared by every path that matches no route.
UNMATCHED_ROUTE = "<unmatched>"


class RouteTemplates:
    """Looks up a handled request's route template. One per middleware."""

    def __init__(self) -> None:
        # id(route) -> full path template. Built on the first request,
        # because routers are included after middleware is added.
        self._templates: dict[int, str] | None = None

    def of(self, scope: Scope) -> str:
        """The route template for a request the app has already routed.

        The router stores the matched route in the scope it was handed,
        which is the middleware's own dict. That route's .path is relative
        to its router's prefix ("/live"), so the full template comes from
        FastAPI's flattened route list.
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
