"""Tests for app/blog/schema.py — request-body validation."""

import pytest
from pydantic import ValidationError

from app.blog.constants import (
    MAX_READ_TIME_SECONDS,
    MAX_SEO_DESCRIPTION_LEN,
    MAX_SEO_TITLE_LEN,
    MAX_TITLE_LEN,
    AdPlacement,
)
from app.blog.schema import BlogCreateRequest, BlogUpdateRequest, BlogViewRequest


class TestBlogCreateRequest:
    def test_valid_minimal(self):
        req = BlogCreateRequest(title="Test", content_html="<p>Hi</p>")
        assert req.title == "Test"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"title": "", "content_html": "<p>Hi</p>"},
            {"title": "T", "content_html": ""},
            {"title": "x" * (MAX_TITLE_LEN + 1), "content_html": "<p>x</p>"},
            {"title": "T", "content_html": "<p>x</p>", "seo_title": "x" * (MAX_SEO_TITLE_LEN + 1)},
            {
                "title": "T",
                "content_html": "<p>x</p>",
                "seo_description": "x" * (MAX_SEO_DESCRIPTION_LEN + 1),
            },
        ],
        ids=[
            "empty_title",
            "empty_content",
            "title_too_long",
            "seo_title_too_long",
            "seo_desc_too_long",
        ],
    )
    def test_boundary_rejections(self, kwargs):
        with pytest.raises(ValidationError):
            BlogCreateRequest(**kwargs)

    def test_defaults(self):
        req = BlogCreateRequest(title="T", content_html="<p>x</p>")
        assert req.is_draft is True
        assert req.monetized is False
        assert req.ad_placement == AdPlacement.NONE

    @pytest.mark.parametrize("value", ["none", "minimal", "standard"])
    def test_ad_placement_accepts_valid(self, value):
        req = BlogCreateRequest(
            title="T",
            content_html="<p>x</p>",
            monetized=True,
            ad_placement=value,
        )
        assert req.ad_placement == value

    @pytest.mark.parametrize("value", ["premium", "banner", "", "STANDARD"])
    def test_ad_placement_rejects_invalid(self, value):
        with pytest.raises(ValidationError):
            BlogCreateRequest(
                title="T",
                content_html="<p>x</p>",
                monetized=True,
                ad_placement=value,
            )


class TestBlogUpdateRequest:
    def test_all_fields_optional(self):
        req = BlogUpdateRequest()
        assert req.title is None
        assert req.content_html is None

    def test_partial_update(self):
        req = BlogUpdateRequest(title="New")
        assert req.title == "New"
        assert req.content_html is None

    def test_boundary_still_enforced(self):
        with pytest.raises(ValidationError):
            BlogUpdateRequest(title="x" * (MAX_TITLE_LEN + 1))


class TestBlogViewRequest:
    def test_default_read_time(self):
        assert BlogViewRequest().read_time_seconds == 0

    def test_custom_read_time(self):
        assert BlogViewRequest(read_time_seconds=45).read_time_seconds == 45

    @pytest.mark.parametrize(
        "value",
        [-1, MAX_READ_TIME_SECONDS + 1, 100 * MAX_READ_TIME_SECONDS],
        ids=["negative", "over_cap", "way_over_cap"],
    )
    def test_boundary_rejections(self, value):
        with pytest.raises(ValidationError):
            BlogViewRequest(read_time_seconds=value)
