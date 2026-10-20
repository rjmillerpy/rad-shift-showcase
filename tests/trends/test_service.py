"""Tests for app/trends/service.py — cache + per-source error isolation."""

import time
from unittest.mock import patch

import pytest

from app.trends import service
from app.trends.schema import (
    SOURCE_GOOGLE,
    SOURCE_HN,
    SOURCE_REDDIT,
    SOURCE_TRENDS24,
    TrendItem,
)


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    service.clear_cache()
    yield
    service.clear_cache()


def _stub_item(source: str, rank: int = 1) -> TrendItem:
    return TrendItem(source=source, rank=rank, keyword=f"kw-{source}-{rank}")


class TestGetTrends:
    def test_returns_bundles_for_all_sources_by_default(self):
        with patch.dict(
            service._FETCHERS,
            {
                SOURCE_TRENDS24: lambda: [_stub_item(SOURCE_TRENDS24)],
                SOURCE_GOOGLE: lambda: [_stub_item(SOURCE_GOOGLE)],
                SOURCE_REDDIT: lambda: [_stub_item(SOURCE_REDDIT)],
                SOURCE_HN: lambda: [_stub_item(SOURCE_HN)],
            },
            clear=True,
        ):
            bundles = service.get_trends(None)

        assert {b.source for b in bundles} == {
            SOURCE_TRENDS24,
            SOURCE_GOOGLE,
            SOURCE_REDDIT,
            SOURCE_HN,
        }

    def test_filters_to_requested_sources(self):
        with patch.dict(
            service._FETCHERS,
            {
                SOURCE_GOOGLE: lambda: [_stub_item(SOURCE_GOOGLE)],
                SOURCE_REDDIT: lambda: [_stub_item(SOURCE_REDDIT)],
            },
            clear=True,
        ):
            bundles = service.get_trends([SOURCE_GOOGLE])

        assert [b.source for b in bundles] == [SOURCE_GOOGLE]

    def test_invalid_source_names_fall_back_to_all(self):
        with patch.dict(service._FETCHERS, {SOURCE_GOOGLE: lambda: []}, clear=True):
            bundles = service.get_trends(["not_a_real_source"])
        assert [b.source for b in bundles] == [SOURCE_GOOGLE]

    def test_fetcher_error_is_captured_in_bundle(self):
        def failing() -> list[TrendItem]:
            raise ConnectionError("boom")

        with patch.dict(service._FETCHERS, {SOURCE_GOOGLE: failing}, clear=True):
            bundles = service.get_trends([SOURCE_GOOGLE])

        assert bundles[0].error == "boom"
        assert bundles[0].items == []

    def test_cache_prevents_second_call_within_ttl(self):
        call_count = {"n": 0}

        def counting() -> list[TrendItem]:
            call_count["n"] += 1
            return [_stub_item(SOURCE_GOOGLE)]

        with patch.dict(service._FETCHERS, {SOURCE_GOOGLE: counting}, clear=True):
            service.get_trends([SOURCE_GOOGLE])
            service.get_trends([SOURCE_GOOGLE])

        assert call_count["n"] == 1

    def test_expired_cache_triggers_refetch(self):
        call_count = {"n": 0}

        def counting() -> list[TrendItem]:
            call_count["n"] += 1
            return [_stub_item(SOURCE_GOOGLE)]

        with patch.dict(service._FETCHERS, {SOURCE_GOOGLE: counting}, clear=True):
            service.get_trends([SOURCE_GOOGLE])
            # Swap the cache entry for a stale copy (responses are immutable).
            stale_at = int(time.time()) - (service.CACHE_TTL_SECONDS + 1)
            service._cache[SOURCE_GOOGLE] = service._cache[SOURCE_GOOGLE].model_copy(
                update={"fetched_at": stale_at}
            )
            service.get_trends([SOURCE_GOOGLE])

        assert call_count["n"] == 2

    def test_clear_cache_forces_refetch(self):
        call_count = {"n": 0}

        def counting() -> list[TrendItem]:
            call_count["n"] += 1
            return [_stub_item(SOURCE_GOOGLE)]

        with patch.dict(service._FETCHERS, {SOURCE_GOOGLE: counting}, clear=True):
            service.get_trends([SOURCE_GOOGLE])
            service.clear_cache()
            service.get_trends([SOURCE_GOOGLE])

        assert call_count["n"] == 2
