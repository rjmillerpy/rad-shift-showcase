"""Per-source trend fetchers. Each exports a single fetch_* callable."""

from .google import fetch_google_trends
from .hackernews import fetch_hn_top
from .reddit import fetch_reddit_popular
from .trends24 import fetch_trends24

__all__ = [
    "fetch_trends24",
    "fetch_google_trends",
    "fetch_reddit_popular",
    "fetch_hn_top",
]
