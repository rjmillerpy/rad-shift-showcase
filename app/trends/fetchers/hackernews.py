"""Fetch top Hacker News front-page stories via the public Algolia API."""

import json
import logging

from app.trends.fetchers._common import MAX_TITLE_CHARS, http_get_text
from app.trends.schema import SOURCE_HN, TrendItem

logger = logging.getLogger(__name__)

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search?tags=front_page"
HN_PERMALINK_TEMPLATE = "https://news.ycombinator.com/item?id={id}"
MAX_ITEMS = 25


def fetch_hn_top() -> list[TrendItem]:
    """Return the top ~20 front-page HN stories ranked by points."""
    hits = _fetch_hits(HN_ALGOLIA_URL)
    return _build_items(hits)


def _fetch_hits(url: str) -> list[dict]:
    text = http_get_text(url, "hn")
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ConnectionError(f"hn returned invalid JSON: {exc}") from exc

    hits = payload.get("hits") or []
    hits.sort(key=lambda h: h.get("points") or 0, reverse=True)
    return hits


def _build_items(hits: list[dict]) -> list[TrendItem]:
    items: list[TrendItem] = []
    for hit in hits[:MAX_ITEMS]:
        title = (hit.get("title") or "").strip()[:MAX_TITLE_CHARS]
        if not title:
            continue
        object_id = hit.get("objectID") or ""
        items.append(
            TrendItem(
                source=SOURCE_HN,
                rank=len(items) + 1,
                keyword=title,
                url=hit.get("url") or HN_PERMALINK_TEMPLATE.format(id=object_id),
                volume=f"{int(hit.get('points') or 0):,} points",
                category=None,
            )
        )
    return items
