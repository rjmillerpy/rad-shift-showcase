"""Aggregation, caching, and error-isolation for trend fetchers."""

import logging
import threading
import time
from collections.abc import Callable

from app.trends.fetchers import (
    fetch_google_trends,
    fetch_hn_top,
    fetch_reddit_popular,
    fetch_trends24,
)
from app.trends.schema import (
    SOURCE_GOOGLE,
    SOURCE_HN,
    SOURCE_LABELS,
    SOURCE_REDDIT,
    SOURCE_TRENDS24,
    SourceTrends,
    TrendItem,
)

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900  # 15 minutes
MAX_ERROR_MESSAGE_CHARS = 500  # cap fetcher-error text stored on a bundle
FetcherFn = Callable[[], list[TrendItem]]

_FETCHERS: dict[str, FetcherFn] = {
    SOURCE_TRENDS24: fetch_trends24,
    SOURCE_GOOGLE: fetch_google_trends,
    SOURCE_REDDIT: fetch_reddit_popular,
    SOURCE_HN: fetch_hn_top,
}

_cache: dict[str, SourceTrends] = {}
_cache_lock = threading.Lock()


def get_trends(sources: list[str] | None = None) -> list[SourceTrends]:
    """Return trend bundles for the requested sources (or all if None).

    Each bundle is fetched from cache if fresh (<15min old); otherwise re-fetched
    and stored. Per-source failures are captured as `error` on the bundle —
    never raised to the caller.
    """
    requested = _resolve_sources(sources)
    return [_get_one(name) for name in requested]


def _resolve_sources(sources: list[str] | None) -> list[str]:
    """Validate and normalize the caller's requested source list."""
    if sources is None:
        return list(_FETCHERS.keys())
    valid = [s for s in sources if s in _FETCHERS]
    return valid or list(_FETCHERS.keys())


def _get_one(source: str) -> SourceTrends:
    """Return a cached bundle or fetch+cache a fresh one."""
    with _cache_lock:
        cached = _cache.get(source)
    if cached and _is_fresh(cached):
        return cached

    bundle = _fetch_source_safely(source)
    with _cache_lock:
        _cache[source] = bundle
    return bundle


def _is_fresh(bundle: SourceTrends) -> bool:
    return (int(time.time()) - bundle.fetched_at) < CACHE_TTL_SECONDS


def _fetch_source_safely(source: str) -> SourceTrends:
    """Fetch a source, catching network/parse errors into an error bundle."""
    fetcher = _FETCHERS[source]
    label = SOURCE_LABELS[source]
    started = int(time.time())
    try:
        items = fetcher()
        return SourceTrends(source=source, label=label, items=items, fetched_at=started, error=None)
    except ConnectionError as exc:
        logger.warning("Trends fetch failed for %s: %s", source, exc)
        return SourceTrends(
            source=source,
            label=label,
            items=[],
            fetched_at=started,
            error=str(exc)[:MAX_ERROR_MESSAGE_CHARS],
        )


def clear_cache() -> None:
    """Drop all cached bundles. Exposed for tests and admin 'refresh' actions."""
    with _cache_lock:
        _cache.clear()
