"""Tests for app/metrics/middleware.py, on a small real app with its own registry."""

import asyncio

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.metrics.middleware import MetricsMiddleware
from app.metrics.service import METRICS_PATH, UNMATCHED_ROUTE

from .conftest import sample_value

# How long the slow route takes; the histogram must see at least this.
_SLOW_SECONDS = 0.05


def _build_app(request_metrics) -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("handler failed")

    @app.get("/slow")
    async def slow() -> dict[str, str]:
        await asyncio.sleep(_SLOW_SECONDS)
        return {}

    @app.get("/stream")
    def stream() -> StreamingResponse:
        return StreamingResponse(iter(["a", "b"]), media_type="text/plain")

    @app.get(METRICS_PATH)
    def scrape() -> dict[str, str]:
        return {}

    nested = APIRouter()

    @nested.get("/{post_id}/likes")
    def likes(post_id: int) -> dict[str, int]:
        return {"id": post_id}

    app.include_router(nested, prefix="/posts")

    app.add_middleware(MetricsMiddleware, metrics=request_metrics)
    return app


@pytest.fixture()
def client(request_metrics):
    # A crashing handler must come back as a 500, as it does in production.
    return TestClient(_build_app(request_metrics), raise_server_exceptions=False)


def _count(request_metrics, route: str, status: str, method: str = "GET") -> float:
    body = request_metrics.render().decode()
    return sample_value(body, "http_requests_total", method=method, route=route, status=status)


class TestRouteLabel:
    def test_uses_the_template_not_the_path(self, client, request_metrics):
        client.get("/items/1")
        client.get("/items/2")
        assert _count(request_metrics, "/items/{item_id}", "200") == 2

    def test_includes_the_router_prefix(self, client, request_metrics):
        """A route's own .path is relative to its router ("/{post_id}/likes")."""
        client.get("/posts/7/likes")
        assert _count(request_metrics, "/posts/{post_id}/likes", "200") == 1

    @pytest.mark.parametrize(
        "path",
        ["/nope", "/wp-login.php", "/items/1/extra"],
        ids=["missing", "scanner-probe", "too-deep"],
    )
    def test_unmatched_paths_share_one_label(self, client, request_metrics, path):
        client.get(path)
        assert _count(request_metrics, UNMATCHED_ROUTE, "404") == 1

    def test_validation_errors_keep_the_route(self, client, request_metrics):
        client.get("/items/not-a-number")
        assert _count(request_metrics, "/items/{item_id}", "422") == 1


class TestStatus:
    def test_handler_exception_counts_as_500(self, client, request_metrics):
        assert client.get("/boom").status_code == 500
        assert _count(request_metrics, "/boom", "500") == 1

    def test_streaming_response_is_counted_once(self, client, request_metrics):
        assert client.get("/stream").text == "ab"
        assert _count(request_metrics, "/stream", "200") == 1

    def test_method_is_a_label(self, client, request_metrics):
        client.post("/items/1")
        assert _count(request_metrics, "/items/{item_id}", "405", method="POST") == 1


class TestLatency:
    def test_measures_the_handler(self, client, request_metrics):
        client.get("/slow")
        body = request_metrics.render().decode()
        labels = {"method": "GET", "route": "/slow"}
        assert sample_value(body, "http_request_duration_seconds_sum", **labels) >= _SLOW_SECONDS


class TestExclusions:
    def test_scrapes_are_not_counted(self, client, request_metrics):
        client.get(METRICS_PATH)
        assert _count(request_metrics, METRICS_PATH, "200") == 0

    def test_non_http_scopes_pass_through(self, client, request_metrics):
        """The lifespan scope (startup/shutdown) goes straight to the app."""
        with client:  # entering runs the lifespan protocol
            pass
        body = request_metrics.render().decode()
        assert all(
            not family.samples
            for family in text_string_to_metric_families(body)
            if family.name == "http_requests"
        )
