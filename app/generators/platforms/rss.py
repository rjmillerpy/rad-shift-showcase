"""RSS/Atom adapter: any public feed becomes a generator source.

platform_config: {"feed_url": "https://…"}. The public edition's platform
(app/baseline.py); it uses the same feed plumbing as the other adapters.
"""

from typing import Any

import feedparser

from ..items import ScrapedItem
from .base import PlatformAdapter, PlatformConfigError
from .feeds import fetch_feed, parse_entries, strip_html

PLATFORM_RSS = "rss"
FEED_URL_KEY = "feed_url"
_ALLOWED_SCHEMES = ("https://", "http://")


class RssAdapter(PlatformAdapter):
    platform = PLATFORM_RSS

    def validate_config(self, platform_config: dict) -> None:
        url = platform_config.get(FEED_URL_KEY)
        if not isinstance(url, str) or not url.startswith(_ALLOWED_SCHEMES):
            raise PlatformConfigError(f"{FEED_URL_KEY} must be an http(s) URL")

    def fetch_items(self, platform_config: dict, max_items: int) -> list[ScrapedItem]:
        self.validate_config(platform_config)
        raw = fetch_feed(platform_config[FEED_URL_KEY], "RSS")
        return parse_entries(feedparser.parse(raw).entries, max_items, build_item)


def build_item(entry: Any) -> ScrapedItem | None:
    """One feed entry as an item; None when it has neither text nor a title."""
    title = (entry.get("title") or "").strip() or None
    text = strip_html(entry.get("summary") or "") or title
    if not text:
        return None
    return ScrapedItem(title=title, text=text, image_url=None, link=entry.get("link"), popularity=0)
