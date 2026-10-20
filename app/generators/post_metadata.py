"""Builders for the ``post_metadata`` JSON written by scraped-content posts.

Scraped posts carry two extra blocks compared to a normal user post:

* ``source`` — where the content came from (platform label, source name, site URL).
  The backend owns the canonical human-readable ``label`` so the frontend doesn't
  need a platform-id-to-label mapping of its own.

* ``link_card`` — the original-post link to render as a card (title, URL, image).

This module is the single source of truth for those shapes; both
``service._post_item`` (the only writer today) and any future writer should call
through here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .items import ScrapedItem
from .models import GeneratorSource
from .platforms.base import PLATFORM_WEB

PLATFORM_LABELS: dict[str, str] = {
    "reddit": "Reddit",
    "pinterest": "Pinterest",
    PLATFORM_WEB: "Web",
}


def _human_platform_label(platform: str) -> str:
    """Return a display label for a platform id, falling back to the raw id."""
    return PLATFORM_LABELS.get(platform, platform.title() if platform else "Web")


def _format_source_label(source: GeneratorSource) -> str:
    """Compose 'Reddit · r/python' or 'Hacker News' style attribution.

    Prefers the source's own ``name`` (admin-configured) as the suffix when set;
    falls back to platform_config hints for platforms where the name and the
    platform identity differ (e.g. reddit: r/<subreddit>).
    """
    platform_label = _human_platform_label(source.platform or PLATFORM_WEB)
    name = (source.name or "").strip()

    # Web sources almost always have a hostname-y or descriptive name already;
    # showing 'Web · {name}' is noisy, so just show the name.
    if (source.platform or PLATFORM_WEB) == PLATFORM_WEB:
        return name or platform_label

    if not name:
        return platform_label
    return f"{platform_label} · {name}"


def _hostname_from_url(url: str | None) -> str | None:
    """Extract a hostname from a URL, returning None when it's not parseable."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").strip()
    return host or None


def build_source_metadata(source: GeneratorSource) -> dict[str, Any]:
    """Build the ``source`` block written into post_metadata for a scraped post."""
    return {
        "platform": source.platform or PLATFORM_WEB,
        "name": (source.name or "").strip(),
        "url": (source.site_url or "").strip() or None,
        "label": _format_source_label(source),
    }


def build_link_card(item: ScrapedItem) -> dict[str, Any] | None:
    """Build the ``link_card`` block from a scraped item.

    Returns None when the item has no link — there's nothing card-worthy then,
    and the frontend should fall back to plain-text rendering.
    """
    if not item.link:
        return None
    return {
        "url": item.link,
        "title": item.title or None,
        "image": item.image_url or None,
        "hostname": _hostname_from_url(item.link),
        "is_video": item.is_video,
    }


def build_scraped_post_metadata(
    source: GeneratorSource,
    item: ScrapedItem,
) -> dict[str, Any]:
    """Combine source + (optional) link_card into a post_metadata dict."""
    metadata: dict[str, Any] = {"source": build_source_metadata(source)}
    link_card = build_link_card(item)
    if link_card is not None:
        metadata["link_card"] = link_card
    return metadata
