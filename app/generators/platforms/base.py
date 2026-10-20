"""Platform adapter contract and lookup.

Each platform (RSS, Reddit, …) is a ``PlatformAdapter``. The edition
(app/plugins.py) decides which adapters exist; the service looks one up with
``get_adapter(platform_name)``.

"web" is the CSS-selector scraper. It isn't an adapter: the edition supplies
it as ``web_scraper`` (app/generators/web.py), and the platform is supported
only when it does.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar

from app.plugins import WEB_PLATFORM, edition

from ..constants import ALL_ENDPOINTS_FAILED_PREFIX
from ..items import ScrapedItem

logger = logging.getLogger(__name__)

PLATFORM_WEB = WEB_PLATFORM


class PlatformConfigError(ValueError):
    """Raised when a source's platform_config dict is missing required fields.

    Service layer catches this and converts it to a 422 — never leak the raw
    message body if it would expose internal field names beyond the public
    schema.
    """


class PlatformAdapter(ABC):
    """Contract every platform fetcher (other than "web") must satisfy."""

    platform: ClassVar[str] = ""

    @abstractmethod
    def validate_config(self, platform_config: dict) -> None:
        """Raise PlatformConfigError if platform_config is missing required keys."""

    @abstractmethod
    def fetch_items(self, platform_config: dict, max_items: int) -> list[ScrapedItem]:
        """Return ScrapedItem objects for this source. Caller applies common filters."""


def _adapters() -> dict[str, PlatformAdapter]:
    return {adapter.platform: adapter for adapter in edition().platform_adapters}


def get_adapter(platform: str) -> PlatformAdapter:
    """Look up the adapter for a platform name, or raise KeyError."""
    adapters = _adapters()
    if platform not in adapters:
        raise KeyError(f"No adapter registered for platform '{platform}'")
    return adapters[platform]


def has_web_scraper() -> bool:
    """True when this edition can scrape arbitrary sites by CSS selector."""
    return edition().web_scraper is not None


def is_platform_supported(platform: str) -> bool:
    """Return True if `platform` is available in this edition."""
    if platform == PLATFORM_WEB:
        return has_web_scraper()
    return platform in _adapters()


def supported_platforms() -> list[str]:
    """All platform names this edition supports, "web" first when present."""
    web = [PLATFORM_WEB] if has_web_scraper() else []
    return [*web, *sorted(_adapters())]


def fetch_with_fallbacks[T](urls: list[str], fetcher: Callable[[str], T]) -> T:
    """Try each URL in order via ``fetcher``; return the first success.

    Used by fragile-platform adapters (X / TikTok / Instagram) whose data
    sources go up and down independently. The caller supplies a ``fetcher``
    that knows how to make the HTTP call and parse the body — this helper
    only owns the order-and-retry logic.

    Each failing attempt is logged at WARNING with the URL so admins can see
    in logs which endpoint died first. If every URL fails, raises a single
    ``ConnectionError`` whose message lists every attempted URL and its
    failure mode — never silently swallows.
    """
    if not urls:
        raise ValueError("fetch_with_fallbacks requires at least one URL")

    failures: list[str] = []
    for url in urls:
        try:
            return fetcher(url)
        except ConnectionError as exc:
            logger.warning("Endpoint failed for %s: %s", url, exc)
            failures.append(f"{url}: {exc}")
    raise ConnectionError(ALL_ENDPOINTS_FAILED_PREFIX + " | ".join(failures))
