"""Fetch trending X topics from trends24.in (plain HTML scrape)."""

import logging

from bs4 import BeautifulSoup, Tag

from app.trends.fetchers._common import http_get_text
from app.trends.schema import SOURCE_TRENDS24, TrendItem

logger = logging.getLogger(__name__)

TRENDS24_URL_TEMPLATE = "https://trends24.in/{region}/"
MAX_ITEMS = 50
TREND_LINK_SELECTOR = "a.trend-link"

_FIREFOX_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Upgrade-Insecure-Requests": "1",
}


def _href(link: Tag) -> str | None:
    """A link's href. bs4 returns a list for multi-valued attributes; href never is."""
    href = link.get("href")
    return href if isinstance(href, str) else None


def fetch_trends24(region: str = "united-states") -> list[TrendItem]:
    """Scrape the top trending X topics for a region.

    Raises ConnectionError on network/HTTP errors. Callers should treat that
    as "source unavailable" and continue with other sources.
    """
    html = http_get_text(
        TRENDS24_URL_TEMPLATE.format(region=region),
        "trends24",
        headers=_FIREFOX_HEADERS,
    )
    return _parse_trend_links(html)


def _parse_trend_links(html: str) -> list[TrendItem]:
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select(TREND_LINK_SELECTOR)[:MAX_ITEMS]
    items: list[TrendItem] = []
    seen: set[str] = set()
    for link in links:
        keyword = link.get_text(strip=True)
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        items.append(
            TrendItem(
                source=SOURCE_TRENDS24,
                rank=len(items) + 1,
                keyword=keyword,
                url=_href(link),
                volume=None,
                category=None,
            )
        )
    return items
