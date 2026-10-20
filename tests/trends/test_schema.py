"""Tests for app/trends/schema.py — Pydantic validation boundaries."""

import pytest
from pydantic import ValidationError

from app.trends.schema import (
    ALL_SOURCES,
    SOURCE_LABELS,
    SourceTrends,
    TrendItem,
    TrendsResponse,
)


class TestTrendItem:
    def test_minimal_valid_item(self):
        item = TrendItem(source="trends24", rank=1, keyword="alpha")
        assert item.url is None
        assert item.volume is None

    @pytest.mark.parametrize(
        "overrides",
        [{"rank": 0}, {"rank": -5}, {"keyword": ""}],
        ids=["rank-zero", "rank-negative", "empty-keyword"],
    )
    def test_rejects_invalid_boundary_values(self, overrides):
        base = {"source": "trends24", "rank": 1, "keyword": "alpha"}
        base.update(overrides)
        with pytest.raises(ValidationError):
            TrendItem(**base)

    def test_keyword_max_length_enforced(self):
        with pytest.raises(ValidationError):
            TrendItem(source="google", rank=1, keyword="x" * 501)


class TestSourceTrends:
    def test_bundle_with_error_allows_empty_items(self):
        bundle = SourceTrends(
            source="google",
            label="Google Search",
            items=[],
            fetched_at=1_700_000_000,
            error="fetch failed",
        )
        assert bundle.items == []


class TestConstants:
    def test_every_source_has_a_label(self):
        assert set(ALL_SOURCES) == set(SOURCE_LABELS.keys())

    def test_response_roundtrip(self):
        response = TrendsResponse(
            sources=[
                SourceTrends(
                    source="google",
                    label="Google Search",
                    items=[TrendItem(source="google", rank=1, keyword="k")],
                    fetched_at=1_700_000_000,
                    error=None,
                )
            ]
        )
        assert response.model_dump()["sources"][0]["items"][0]["keyword"] == "k"
