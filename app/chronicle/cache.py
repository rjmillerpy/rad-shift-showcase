"""In-process TTL cache for generated chronicles.

Keyed on the ordered set of post ids (so re-requesting the same page returns a
cache hit; a different set of posts recomputes) and on how it was narrated:
users with and without the chronicle-llm-narration flag see different text
for the same posts, so neither may be served the other's.
"""

import hashlib
import time
from typing import Any

from app.chronicle.constants import CHRONICLE_CACHE_SECONDS
from app.posts.schema import PostResponse

_cache: dict[str, dict[str, Any]] = {}

NARRATED_MODE = "llm"
FALLBACK_MODE = "rules"


def cache_key_for(posts: list[PostResponse], *, narrated: bool) -> str:
    """Return the cache key for a list of posts, ordered, and the narration mode."""
    mode = NARRATED_MODE if narrated else FALLBACK_MODE
    joined = mode + ":" + ",".join(str(p.id) for p in posts)
    # A cache key, not a security boundary; usedforsecurity=False also keeps it
    # working on FIPS-mode systems that block MD5 for security use.
    return hashlib.md5(joined.encode(), usedforsecurity=False).hexdigest()


def get(cache_key: str) -> list[dict] | None:
    """Return cached segments if present and fresh, else None."""
    entry = _cache.get(cache_key)
    if entry is None:
        return None
    if time.time() - entry["generated_at"] >= CHRONICLE_CACHE_SECONDS:
        return None
    return entry["segments"]


def store(cache_key: str, segments: list[dict]) -> None:
    _cache[cache_key] = {"segments": segments, "generated_at": time.time()}


def clear() -> None:
    """Drop all cached chronicles. Intended for tests."""
    _cache.clear()
