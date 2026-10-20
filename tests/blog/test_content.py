"""Tests for app/blog/content.py — slug, HTML strip, SEO helpers."""

import pytest

from app.blog import content
from app.blog.constants import (
    MAX_SLUG_LEN,
    SEO_DESC_ELLIPSIS,
    SEO_DESC_MAX_LEN,
    WORDS_PER_MINUTE,
)


class TestSanitizeHtml:
    @pytest.mark.parametrize(
        "dirty,forbidden",
        [
            ("<p>hi</p><script>alert(1)</script>", "<script"),
            ('<img src="x" onerror="alert(1)">', "onerror"),
            ('<a href="javascript:alert(1)">x</a>', "javascript:"),
            ('<iframe src="https://evil.example"></iframe>', "<iframe"),
            ('<p style="x" onclick="steal()">x</p>', "onclick"),
        ],
    )
    def test_removes_active_content(self, dirty, forbidden):
        assert forbidden not in content.sanitize_html(dirty)

    def test_keeps_ordinary_formatting(self):
        html = '<h2>T</h2><p><b>b</b> <a href="https://x.com">l</a></p><ul><li>i</li></ul>'
        clean = content.sanitize_html(html)
        for fragment in ("<h2>T</h2>", "<b>b</b>", 'href="https://x.com"', "<li>i</li>"):
            assert fragment in clean


class TestGenerateSlug:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Hello World", "hello-world"),
            ("Test!@#$%^&*()", "test"),
            ("Multiple   Spaces", "multiple-spaces"),
            ("---dashes---", "-dashes-"),
            ("MIXED Case Title", "mixed-case-title"),
        ],
        ids=["simple", "punctuation", "spaces", "dashes", "mixed_case"],
    )
    def test_slug_shape(self, title, expected):
        assert content.generate_slug(title) == expected

    def test_slug_length_capped(self):
        long_title = "word " * 500
        slug = content.generate_slug(long_title)
        assert len(slug) <= MAX_SLUG_LEN


class TestEstimateReadingTime:
    @pytest.mark.parametrize(
        "word_count,expected",
        [
            (0, 1),
            (50, 1),
            (WORDS_PER_MINUTE, 1),
            (WORDS_PER_MINUTE * 2, 2),
            (WORDS_PER_MINUTE * 5, 5),
        ],
        ids=["empty", "50w", "one_minute", "two_minutes", "five_minutes"],
    )
    def test_minutes(self, word_count, expected):
        text = " ".join(["word"] * word_count)
        assert content.estimate_reading_time(text) == expected

    def test_always_at_least_one(self):
        assert content.estimate_reading_time("") == 1


class TestStripHtml:
    @pytest.mark.parametrize(
        "html,expected",
        [
            ("<p>Hello</p>", "Hello"),
            ("<b>Bold</b> and <i>italic</i>", "Bold and italic"),
            ("<p>   multi\n  spaces   </p>", "multi spaces"),
            ("", ""),
            ("plain text", "plain text"),
        ],
        ids=["p_tag", "nested", "whitespace_collapse", "empty", "no_tags"],
    )
    def test_stripping(self, html, expected):
        assert content.strip_html(html) == expected


class TestAutoSeoDescription:
    def test_short_content_returned_verbatim(self):
        html = "<p>Short body</p>"
        assert content.auto_seo_description(html) == "Short body"

    def test_long_content_truncated_with_ellipsis(self):
        long_body = "A" * (SEO_DESC_MAX_LEN + 100)
        result = content.auto_seo_description(f"<p>{long_body}</p>")
        assert len(result) == SEO_DESC_MAX_LEN
        assert result.endswith(SEO_DESC_ELLIPSIS)

    def test_boundary_length_no_truncation(self):
        exact = "x" * SEO_DESC_MAX_LEN
        assert content.auto_seo_description(f"<p>{exact}</p>") == exact
