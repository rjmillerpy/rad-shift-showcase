"""The "web" platform's contract: scrape an arbitrary site by CSS selector.

An edition (app/plugins.py) may supply a ``WebScraper``; without one the
"web" platform is unsupported and the service answers 422. The service only
calls these four methods.
"""

from typing import Protocol

from fastapi import HTTPException

from app.plugins import edition

from .constants import WEB_SCRAPING_UNAVAILABLE
from .items import ScrapedItem


class WebScraper(Protocol):
    def fetch_page(self, url: str, *, use_browser: bool, browser_engine: str) -> str:
        """The page's HTML; raises ConnectionError when it can't be fetched."""
        ...

    def extract_items(self, html: str, selectors: dict) -> list[ScrapedItem]:
        """Items found in `html` with the source's selectors."""
        ...

    def analyze_page(
        self, url: str, content_hint: str, *, use_browser: bool, browser_engine: str
    ) -> dict:
        """Selectors for a page the source hasn't been set up for yet."""
        ...

    def heal_selectors(
        self,
        url: str,
        old_selectors: dict,
        content_hint: str,
        *,
        use_browser: bool,
        browser_engine: str,
    ) -> dict | None:
        """New selectors after the old ones stopped matching, or None."""
        ...


def web_scraper() -> WebScraper:
    """This edition's web scraper, or a 422 when it has none."""
    scraper = edition().web_scraper
    if scraper is None:
        raise HTTPException(status_code=422, detail=WEB_SCRAPING_UNAVAILABLE)
    return scraper
