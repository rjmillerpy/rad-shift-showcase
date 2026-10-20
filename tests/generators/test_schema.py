"""Tests for generator Pydantic schemas — validation, boundaries, defaults."""

import pytest
from pydantic import ValidationError

from app.generators.schema import (
    AnalyzeRequest,
    ProfileCreateRequest,
    RunSourceRequest,
    SelectorConfig,
    SourceConfig,
    SourceCreateRequest,
    SourceUpdateRequest,
)

# ── SelectorConfig ─────────────────────────────────────────────────────


class TestSelectorConfig:
    def test_valid_minimal(self):
        cfg = SelectorConfig(post_container="div.post", text="p.body")
        assert cfg.post_container == "div.post"
        assert cfg.text == "p.body"
        assert cfg.title is None
        assert cfg.image is None
        assert cfg.link is None
        assert cfg.popularity is None

    def test_valid_full(self):
        cfg = SelectorConfig(
            post_container="article",
            text=".content",
            title="h2",
            image="img.thumb",
            link="a.permalink",
            popularity=".score",
        )
        assert cfg.title == "h2"
        assert cfg.image == "img.thumb"

    def test_missing_post_container(self):
        with pytest.raises(ValidationError):
            SelectorConfig(text="p")

    def test_missing_text(self):
        with pytest.raises(ValidationError):
            SelectorConfig(post_container="div")


# ── SourceConfig ────────────────────────────────────────────────────────


class TestSourceConfig:
    def test_defaults(self):
        cfg = SourceConfig()
        assert cfg.content_types == ["text"]
        assert cfg.max_items_per_run == 10
        assert cfg.min_popularity == 0
        assert cfg.dedupe_field == "text"
        assert cfg.include_keywords == []
        assert cfg.exclude_keywords == []

    @pytest.mark.parametrize(
        "value",
        [1, 50, 100],
        ids=["min-boundary", "mid-range", "max-boundary"],
    )
    def test_max_items_valid(self, value):
        cfg = SourceConfig(max_items_per_run=value)
        assert cfg.max_items_per_run == value

    @pytest.mark.parametrize(
        "value",
        [0, -1, 101],
        ids=["zero", "negative", "above-max"],
    )
    def test_max_items_invalid(self, value):
        with pytest.raises(ValidationError):
            SourceConfig(max_items_per_run=value)

    def test_min_popularity_negative(self):
        with pytest.raises(ValidationError):
            SourceConfig(min_popularity=-1)


# ── SourceCreateRequest ────────────────────────────────────────────────


class TestSourceCreateRequest:
    def test_valid_minimal(self):
        req = SourceCreateRequest(name="My Source", site_url="https://example.com")
        assert req.name == "My Source"
        assert req.run_interval_minutes == 0
        assert req.config is None

    def test_valid_with_config(self):
        req = SourceCreateRequest(
            name="Test",
            site_url="https://example.com",
            config={"max_items_per_run": 5},
        )
        assert req.config.max_items_per_run == 5

    @pytest.mark.parametrize(
        "field,value,reason",
        [
            ("name", "", "empty-name"),
            ("name", "x" * 201, "name-too-long"),
            ("site_url", "", "empty-url"),
            ("site_url", "x" * 2001, "url-too-long"),
        ],
        ids=lambda x: x if isinstance(x, str) and len(x) < 30 else None,
    )
    def test_invalid_fields(self, field, value, reason):
        kwargs = {"name": "ok", "site_url": "https://ok.com"}
        kwargs[field] = value
        with pytest.raises(ValidationError):
            SourceCreateRequest(**kwargs)

    @pytest.mark.parametrize(
        "minutes",
        [0, 720, 1440],
        ids=["zero-manual", "half-day", "max-daily"],
    )
    def test_run_interval_valid(self, minutes):
        req = SourceCreateRequest(name="x", site_url="https://x.com", run_interval_minutes=minutes)
        assert req.run_interval_minutes == minutes

    def test_run_interval_too_large(self):
        with pytest.raises(ValidationError):
            SourceCreateRequest(name="x", site_url="https://x.com", run_interval_minutes=1441)

    def test_run_interval_negative(self):
        with pytest.raises(ValidationError):
            SourceCreateRequest(name="x", site_url="https://x.com", run_interval_minutes=-1)


# ── SourceUpdateRequest ────────────────────────────────────────────────


class TestSourceUpdateRequest:
    def test_all_none_is_valid(self):
        req = SourceUpdateRequest()
        assert req.name is None
        assert req.is_active is None

    def test_partial_update(self):
        req = SourceUpdateRequest(name="New Name", is_active=False)
        assert req.name == "New Name"
        assert req.is_active is False

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            SourceUpdateRequest(name="x" * 201)


# ── ProfileCreateRequest ───────────────────────────────────────────────


class TestProfileCreateRequest:
    def test_valid(self):
        req = ProfileCreateRequest(source_id=1, user_id=2)
        assert req.source_id == 1
        assert req.user_id == 2

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            ProfileCreateRequest(source_id=1)


# ── RunSourceRequest ───────────────────────────────────────────────────


class TestRunSourceRequest:
    def test_valid(self):
        req = RunSourceRequest(source_id=42)
        assert req.source_id == 42

    def test_missing_source_id(self):
        with pytest.raises(ValidationError):
            RunSourceRequest()


# ── AnalyzeRequest ──────────────────────────────────────────────────────


class TestAnalyzeRequest:
    def test_valid_minimal(self):
        req = AnalyzeRequest(site_url="https://example.com")
        assert req.content_hint is None

    def test_valid_with_hint(self):
        req = AnalyzeRequest(site_url="https://example.com", content_hint="memes")
        assert req.content_hint == "memes"

    def test_hint_too_long(self):
        with pytest.raises(ValidationError):
            AnalyzeRequest(site_url="https://example.com", content_hint="x" * 501)

    def test_empty_url(self):
        with pytest.raises(ValidationError):
            AnalyzeRequest(site_url="")
