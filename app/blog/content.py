"""Content helpers for blog posts — slug, HTML stripping, SEO derivation."""

import re

import nh3

from app.blog.constants import (
    MAX_SLUG_LEN,
    SEO_DESC_ELLIPSIS,
    SEO_DESC_MAX_LEN,
    SEO_DESC_TRUNCATE_AT,
    WORDS_PER_MINUTE,
)

_SLUG_ALLOWED_RE = re.compile(r"[^a-zA-Z0-9\s-]")
_SLUG_SPACE_RE = re.compile(r"[\s]+")
_SLUG_DASH_COLLAPSE_RE = re.compile(r"-+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def generate_slug(title: str) -> str:
    """Generate URL-safe slug from title."""
    slug = _SLUG_ALLOWED_RE.sub("", title.lower())
    slug = _SLUG_SPACE_RE.sub("-", slug.strip())
    slug = _SLUG_DASH_COLLAPSE_RE.sub("-", slug)
    return slug[:MAX_SLUG_LEN]


def estimate_reading_time(text: str) -> int:
    """Estimate reading time in minutes from plain text."""
    words = len(text.split())
    return max(1, round(words / WORDS_PER_MINUTE))


def sanitize_html(html: str) -> str:
    """Strip scripts, event-handler attributes, and unsafe URL schemes.

    Blog HTML is rendered with `dangerouslySetInnerHTML` on the frontend, so
    it must be made safe before it is stored. nh3's default allowlist keeps
    ordinary formatting (headings, lists, links, images, code, quotes).
    """
    return nh3.clean(html)


def strip_html(html: str) -> str:
    """Basic HTML tag stripping for plain text extraction."""
    clean = _HTML_TAG_RE.sub("", html)
    return _WHITESPACE_RE.sub(" ", clean).strip()


def auto_seo_description(html: str) -> str:
    """Generate a SEO description from the first characters of content."""
    plain = strip_html(html)
    if len(plain) <= SEO_DESC_MAX_LEN:
        return plain
    return plain[:SEO_DESC_TRUNCATE_AT] + SEO_DESC_ELLIPSIS
