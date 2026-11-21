"""Tests for app/logs/constants.py."""

import pytest
from fastapi.routing import iter_route_contexts

from app.logs.constants import (
    DEFAULT_LOG_LEVEL,
    JSON_RENDERER,
    QUIET_ROUTES,
    REQUEST_ID_PATTERN,
)
from app.main import app


class TestRequestIdPattern:
    # Fixed values: parallel test workers must all collect the same test ids.
    @pytest.mark.parametrize(
        "value",
        ["3f2a9c1e-7d4b-4e8a-9b1c-2d3e4f5a6b7c", "3f2a9c1e7d4b4e8a9b1c2d3e4f5a6b7c", "edge.req_42"],
    )
    def test_ids_from_common_sources_fit(self, value):
        assert REQUEST_ID_PATTERN.fullmatch(value)

    @pytest.mark.parametrize("value", ["a\nb", 'a"b', "a b", "", "x" * 129, "é"])
    def test_anything_that_could_forge_or_bloat_a_line_does_not(self, value):
        assert not REQUEST_ID_PATTERN.fullmatch(value)


def test_every_quiet_route_is_a_real_route():
    """A renamed health route would otherwise quietly start logging at INFO."""
    paths = {context.path for context in iter_route_contexts(app.routes)}
    assert paths >= QUIET_ROUTES


def test_defaults_are_production_safe():
    assert (JSON_RENDERER, DEFAULT_LOG_LEVEL) == ("json", "INFO")
