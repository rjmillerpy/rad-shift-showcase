"""Tests for app/common/route_templates.py, on a small real app."""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.common.route_templates import UNMATCHED_ROUTE, RouteTemplates


def _app_recording_templates(seen: list[str]) -> FastAPI:
    app = FastAPI()
    templates = RouteTemplates()

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    nested = APIRouter()

    @nested.get("/live")
    def live() -> dict[str, str]:
        return {}

    app.include_router(nested, prefix="/health")

    @app.middleware("http")
    async def record(request, call_next):
        response = await call_next(request)
        seen.append(templates.of(request.scope))
        return response

    return app


def test_the_template_not_the_raw_path():
    seen: list[str] = []
    TestClient(_app_recording_templates(seen)).get("/items/123")
    assert seen == ["/items/{item_id}"]


def test_a_routers_prefix_is_included():
    """The route's own .path is "/live"; the template must be the full path."""
    seen: list[str] = []
    TestClient(_app_recording_templates(seen)).get("/health/live")
    assert seen == ["/health/live"]


def test_a_path_no_route_matches():
    seen: list[str] = []
    TestClient(_app_recording_templates(seen)).get("/nope/1")
    assert seen == [UNMATCHED_ROUTE]


def test_a_route_from_another_app_is_unmatched():
    """A route object this app's route list doesn't hold."""
    other = FastAPI()

    @other.get("/elsewhere")
    def elsewhere() -> None:
        return None

    host = FastAPI()
    scope = {"route": other.routes[-1], "app": host}
    assert RouteTemplates().of(scope) == UNMATCHED_ROUTE
