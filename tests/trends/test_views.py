"""Tests for app/trends/views.py — public /trends REST endpoints."""

from unittest.mock import patch

import pytest

from app.trends import service
from app.trends.schema import SOURCE_GOOGLE, SOURCE_TRENDS24, TrendItem


@pytest.fixture(autouse=True)
def _clear_cache():
    service.clear_cache()
    yield
    service.clear_cache()


def _patched_fetchers():
    return {
        SOURCE_TRENDS24: lambda: [TrendItem(source=SOURCE_TRENDS24, rank=1, keyword="x-trend")],
        SOURCE_GOOGLE: lambda: [TrendItem(source=SOURCE_GOOGLE, rank=1, keyword="g-trend")],
    }


class TestListTrends:
    def test_no_auth_required(self, client):
        with patch.dict(service._FETCHERS, _patched_fetchers(), clear=True):
            resp = client.get("/trends/")
        assert resp.status_code == 200

    def test_returns_all_sources_by_default(self, client):
        with patch.dict(service._FETCHERS, _patched_fetchers(), clear=True):
            resp = client.get("/trends/")
        body = resp.json()
        sources = {s["source"] for s in body["sources"]}
        assert sources == {SOURCE_TRENDS24, SOURCE_GOOGLE}

    def test_sources_query_param_filters(self, client):
        with patch.dict(service._FETCHERS, _patched_fetchers(), clear=True):
            resp = client.get(f"/trends/?sources={SOURCE_GOOGLE}")
        body = resp.json()
        assert [s["source"] for s in body["sources"]] == [SOURCE_GOOGLE]
        assert body["sources"][0]["items"][0]["keyword"] == "g-trend"

    @pytest.mark.parametrize(
        "query", ["", "   ", "unknown_source,other_bad"], ids=["empty", "whitespace", "all-invalid"]
    )
    def test_empty_or_invalid_source_list_returns_all(self, client, query):
        with patch.dict(service._FETCHERS, _patched_fetchers(), clear=True):
            resp = client.get(f"/trends/?sources={query}")
        body = resp.json()
        assert {s["source"] for s in body["sources"]} == {SOURCE_TRENDS24, SOURCE_GOOGLE}

    def test_response_item_shape(self, client):
        with patch.dict(service._FETCHERS, _patched_fetchers(), clear=True):
            resp = client.get(f"/trends/?sources={SOURCE_TRENDS24}")
        item = resp.json()["sources"][0]["items"][0]
        assert set(item.keys()) >= {"source", "rank", "keyword", "url", "volume", "category"}


class TestSourcesQueryCap:
    def test_over_cap_rejected(self, client):
        """`?sources=...` must reject a query string longer than the configured cap."""
        from app.trends.views import MAX_SOURCES_QUERY_CHARS

        over = "x" * (MAX_SOURCES_QUERY_CHARS + 1)
        resp = client.get(f"/trends/?sources={over}")
        assert resp.status_code == 422


class TestRefreshTrends:
    def test_refresh_clears_cache_and_refetches(self, client):
        call_count = {"n": 0}

        def counting() -> list[TrendItem]:
            call_count["n"] += 1
            return [TrendItem(source=SOURCE_GOOGLE, rank=1, keyword="fresh")]

        with patch.dict(service._FETCHERS, {SOURCE_GOOGLE: counting}, clear=True):
            client.get(f"/trends/?sources={SOURCE_GOOGLE}")
            first = call_count["n"]
            client.post("/trends/refresh")
            second = call_count["n"]

        assert first == 1
        assert second > first
