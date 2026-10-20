"""RSS plumbing shared by the feed-based adapters: download a feed safely,
and turn its entries into items.

Each adapter keeps only what's specific to it: the feed URL and how one
entry becomes a ScrapedItem.
"""

import re
from collections.abc import Callable
from typing import Any

import httpx

from ..items import ScrapedItem

FEED_TIMEOUT_SECONDS = 15
USER_AGENT = "rad-shift-generator/1.0 (+https://rad-shift.local)"
# A feed is a few hundred KB at most; anything bigger is a mistake or an attack.
MAX_FEED_RESPONSE_BYTES = 5 * 1024 * 1024
_HTML_TAG_REGEX = re.compile(r"<[^>]+>")


def fetch_feed(url: str, source: str) -> bytes:
    """The feed's raw bytes (feedparser handles the XML). Network and HTTP
    errors become ConnectionError, naming `source` (e.g. "Pinterest"), so
    callers catch one exception type."""
    try:
        with httpx.Client(timeout=FEED_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            content_length = int(response.headers.get("content-length", 0))
            if content_length > MAX_FEED_RESPONSE_BYTES:
                raise ValueError(f"Feed too large: {content_length} bytes")
            return response.content
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout fetching {source} feed {url}") from exc
    except httpx.HTTPStatusError as exc:
        raise ConnectionError(f"HTTP {exc.response.status_code} from {source} feed {url}") from exc


def parse_entries(
    entries: list[Any], max_items: int, build: Callable[[Any], ScrapedItem | None]
) -> list[ScrapedItem]:
    """Up to `max_items` entries through `build`, skipping the ones it rejects (None)."""
    items = (build(entry) for entry in entries[:max_items])
    return [item for item in items if item is not None]


def strip_html(html: str) -> str:
    """Cheap HTML to text for RSS <description> fields."""
    return _HTML_TAG_REGEX.sub("", html).replace("&nbsp;", " ").strip()
