"""Regression tests for the response-schema contract (code-quality rule 46).

What broke before: 97 endpoints returned raw dicts, so the API docs showed
"object" for every response, nothing checked what an endpoint really sent,
and a renamed key could reach the frontend unnoticed.

How it stays fixed: every JSON endpoint must declare a named response model,
every response model must be immutable, and the edge cases found while
converting (nullable timestamps, endpoints no test returned 200 from) are
pinned below.
"""

import importlib
import inspect
import pkgutil

import pytest
from pydantic import BaseModel

import app
from app.common.schema import FrozenModel
from app.main import create_app
from app.posts.models import PostModel

_SUCCESS_RESPONSES = [
    (method.upper(), path, status, response)
    for path, operations in create_app().openapi()["paths"].items()
    for method, operation in operations.items()
    for status, response in operation["responses"].items()
    if status.startswith("2")
]

# Endpoints that deliberately don't return JSON, with the media type they declare.
_NON_JSON = {
    ("GET", "/avatar/preview"): "image/png",
    ("GET", "/posts/chronicle/stream"): "text/event-stream",
    ("GET", "/widgets/{widget_id}/render"): "text/html",
    ("GET", "/widgets/{widget_id}/sandbox"): "text/html",
}


def schema_modules(package):
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        if info.name.rsplit(".", 1)[-1] in ("schema", "admin_schema"):
            yield importlib.import_module(info.name)


def response_models(package=app):
    """Classes in <package>/**/schema.py that describe something the API sends."""
    suffixes = ("Response", "Out", "Row", "Summary", "Detail", "Preview")
    for module in schema_modules(package):
        for name, cls in inspect.getmembers(module, inspect.isclass):
            is_local_model = cls.__module__ == module.__name__ and issubclass(cls, BaseModel)
            if is_local_model and name.endswith(suffixes):
                yield cls


class TestEveryEndpointDeclaresItsResponse:
    @pytest.mark.parametrize(
        ("method", "path", "status", "response"),
        _SUCCESS_RESPONSES,
        ids=[f"{method} {path} {status}" for method, path, status, _ in _SUCCESS_RESPONSES],
    )
    def test_success_response_is_a_named_schema_or_a_declared_media_type(
        self, method, path, status, response
    ):
        content = response.get("content", {})
        if (method, path) in _NON_JSON:
            assert list(content) == [_NON_JSON[(method, path)]]
        elif status == "204":
            assert content == {}
        else:
            schema = content["application/json"]["schema"]
            assert "$ref" in schema, f"{method} {path} returns an unnamed object: {schema}"

    def test_the_non_json_list_has_no_stale_entries(self):
        declared = {(method, path) for method, path, _, _ in _SUCCESS_RESPONSES}
        assert set(_NON_JSON) <= declared


class TestResponseModelsAreImmutable:
    @pytest.mark.parametrize("model", list(response_models()), ids=lambda model: model.__name__)
    def test_response_model_is_frozen(self, model):
        """Rule 59: a response is a value; nothing should edit it after the
        service built it."""
        assert issubclass(model, FrozenModel), f"{model.__name__} should extend FrozenModel"

    def test_the_scan_actually_finds_models(self):
        assert len(list(response_models())) > 50


class TestEdgeCasesFoundDuringConversion:
    def test_a_post_without_a_timestamp_does_not_break_the_feed(
        self, client, create_user, create_post, db_session
    ):
        """posts.unix_timestamp is nullable. A strict `int` in the response
        schema would turn one legacy row into a 500 for the whole feed."""
        post = create_post(user=create_user(username="legacy"), text="old row")
        db_session.query(PostModel).filter_by(id=post.id).update({"unix_timestamp": None})
        db_session.commit()

        resp = client.get(f"/posts/{post.id}")

        assert resp.status_code == 200
        assert resp.json()["post"]["unix_timestamp"] is None
