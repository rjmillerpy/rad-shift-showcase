"""Tests for app/logs/middleware.py, on a small real app with production logging."""

import logging
import re
from pathlib import Path

import pytest
import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.common.route_templates import UNMATCHED_ROUTE
from app.logs.constants import LOG_EVENT_REQUEST, REQUEST_ID_HEADER
from app.logs.middleware import USER_STATE_KEY, RequestLogMiddleware

handler_logger = logging.getLogger("radshift.test.handler")
ALLOY_CONFIG = Path(__file__).parents[2] / "observability" / "alloy" / "config.alloy"


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    def sync_item(item_id: int) -> dict[str, int]:
        # Sync handlers run in a worker thread; the request id must follow.
        handler_logger.info("sync.handler")
        return {"id": item_id}

    @app.get("/async")
    async def async_item() -> dict[str, str]:
        handler_logger.info("async.handler")
        return {}

    @app.get("/me")
    def me(request: Request) -> dict[str, str]:
        setattr(request.state, USER_STATE_KEY, "alice")
        return {}

    @app.get("/binds-extra")
    async def binds_extra() -> dict[str, str]:
        structlog.contextvars.bind_contextvars(leftover="from an earlier request")
        return {}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("handler failed")

    @app.get("/teapot", status_code=503)
    def unavailable() -> dict[str, str]:
        return {}

    @app.get("/stream")
    def stream() -> StreamingResponse:
        return StreamingResponse(iter(["a", "b"]), media_type="text/plain")

    @app.get("/breaks-mid-stream")
    def breaks_mid_stream() -> StreamingResponse:
        def chunks():
            yield "a"
            raise RuntimeError("stream failed")

        return StreamingResponse(chunks(), media_type="text/plain")

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {}

    nested = APIRouter()

    @nested.get("/{post_id}/likes")
    def likes(post_id: int) -> dict[str, int]:
        return {"id": post_id}

    app.include_router(nested, prefix="/posts")
    app.add_middleware(RequestLogMiddleware)
    return app


@pytest.fixture()
def client() -> TestClient:
    # A crashing handler must come back as a 500, as it does in production.
    return TestClient(_build_app(), raise_server_exceptions=False)


def _request_lines(lines: list[dict]) -> list[dict]:
    return [line for line in lines if line["event"] == LOG_EVENT_REQUEST]


class TestRequestId:
    def test_a_new_id_when_the_caller_sends_none(self, client):
        response = client.get("/async")
        request_id = response.headers[REQUEST_ID_HEADER]
        assert len(request_id) == 32 and int(request_id, 16) >= 0

    def test_each_request_gets_its_own_id(self, client):
        first, second = client.get("/async"), client.get("/async")
        assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]

    @pytest.mark.parametrize("caller_id", ["3f2a9c1e-7d4b-4e8a-9b1c-2d3e4f5a6b7c", "edge.req_42"])
    def test_a_well_formed_caller_id_is_kept(self, client, caller_id):
        response = client.get("/async", headers={REQUEST_ID_HEADER: caller_id})
        assert response.headers[REQUEST_ID_HEADER] == caller_id

    @pytest.mark.parametrize(
        "caller_id",
        ['abc" "level": "error', "a b", "x" * 129, ""],
        ids=["quote", "space", "long", "empty"],
    )
    def test_anything_else_is_replaced(self, client, caller_id):
        response = client.get("/async", headers={REQUEST_ID_HEADER: caller_id})
        assert response.headers[REQUEST_ID_HEADER] != caller_id
        assert len(response.headers[REQUEST_ID_HEADER]) == 32

    @pytest.mark.parametrize("path", ["/items/1", "/async"])
    def test_lines_logged_by_the_handler_carry_the_id(self, client, json_logs, path):
        response = client.get(path)
        handler_line = next(line for line in json_logs() if line["event"].endswith(".handler"))
        assert handler_line["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_context_from_one_request_does_not_reach_the_next(self, client, json_logs):
        client.get("/binds-extra")
        json_logs()
        client.get("/async")
        assert all("leftover" not in line for line in json_logs())


class TestRequestLine:
    def test_one_line_per_request_with_the_route_template(self, client, json_logs):
        response = client.get("/posts/42/likes")
        (line,) = _request_lines(json_logs())
        assert line["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert line["method"] == "GET"
        assert line["route"] == "/posts/{post_id}/likes"
        assert line["status"] == 200
        assert line["level"] == "info"
        assert line["duration_ms"] >= 0
        assert line[USER_STATE_KEY] is None

    def test_an_unmatched_path_shares_one_route_value(self, client, json_logs):
        client.get("/wp-admin/setup.php")
        (line,) = _request_lines(json_logs())
        assert (line["route"], line["status"]) == (UNMATCHED_ROUTE, 404)

    def test_the_user_left_on_the_request_is_logged(self, client, json_logs):
        client.get("/me")
        assert _request_lines(json_logs())[0][USER_STATE_KEY] == "alice"

    def test_a_server_error_status_is_logged_at_error(self, client, json_logs):
        client.get("/teapot")
        (line,) = _request_lines(json_logs())
        assert (line["status"], line["level"]) == (503, "error")

    def test_health_checks_are_logged_at_debug(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            client.get("/health/live")
        (record,) = [r for r in caplog.records if r.getMessage() == LOG_EVENT_REQUEST]
        assert record.levelno == logging.DEBUG

    def test_a_streamed_response_is_logged_once_and_not_buffered(self, client, json_logs):
        response = client.get("/stream")
        assert response.text == "ab"
        assert response.headers[REQUEST_ID_HEADER]
        assert len(_request_lines(json_logs())) == 1


class TestUnhandledException:
    def test_the_500_carries_the_request_id(self, client):
        response = client.get("/boom")
        assert response.status_code == 500
        assert response.text == "Internal Server Error"
        assert len(response.headers[REQUEST_ID_HEADER]) == 32

    def test_it_is_logged_at_error_with_status_500(self, client, json_logs):
        response = client.get("/boom")
        (line,) = _request_lines(json_logs())
        assert (line["status"], line["level"]) == (500, "error")
        assert line["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_a_failure_after_the_response_started_sends_nothing_more(self, client, json_logs):
        """The 200 and its headers are already on the wire; a second response would be invalid."""
        response = client.get("/breaks-mid-stream")
        assert response.status_code == 200
        (line,) = _request_lines(json_logs())
        assert line["status"] == 200

    def test_the_exception_still_propagates(self):
        """So the server logs the traceback (inside the request's context)."""
        with pytest.raises(RuntimeError, match="handler failed"):
            TestClient(_build_app()).get("/boom")


class TestLokiPipeline:
    def test_every_field_alloy_extracts_is_on_the_request_line(self, client, json_logs):
        """Alloy silently labels nothing if a field it reads is renamed here."""
        block = re.search(r"expressions\s*=\s*\{([^}]*)\}", ALLOY_CONFIG.read_text())
        assert block is not None
        extracted = set(re.findall(r"(\w+)\s*=", block.group(1)))
        client.get("/async")
        (line,) = _request_lines(json_logs())
        # trace_id is on a line only when the request is traced (item 26).
        assert extracted == {"level", "request_id", "trace_id"}
        assert extracted - {"trace_id"} <= set(line)


class TestOtherScopes:
    def test_lifespan_passes_through(self):
        with TestClient(_build_app()) as client:
            assert client.get("/async").status_code == 200
