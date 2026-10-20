"""Tests for app/chronicle/cache.py — TTL cache keyed on post ids."""

import time

import pytest

from app.chronicle import cache
from tests.chronicle.helpers import make_post as _post


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestCacheKey:
    def test_same_posts_same_key(self):
        # Equal but separate lists: the key depends on the ids, not the objects.
        first = [_post(id=1), _post(id=2)]
        second = [_post(id=1), _post(id=2)]
        assert cache.cache_key_for(first, narrated=True) == cache.cache_key_for(
            second, narrated=True
        )

    def test_different_order_different_key(self):
        a = [_post(id=1), _post(id=2)]
        b = [_post(id=2), _post(id=1)]
        assert cache.cache_key_for(a, narrated=True) != cache.cache_key_for(b, narrated=True)

    def test_different_ids_different_key(self):
        a = [_post(id=1)]
        b = [_post(id=99)]
        assert cache.cache_key_for(a, narrated=True) != cache.cache_key_for(b, narrated=True)

    def test_llm_and_rule_based_narration_never_share_a_key(self):
        """A flag-off user's rule-based text must not be served to a flag-on user, or the reverse."""
        posts = [_post(id=1), _post(id=2)]
        assert cache.cache_key_for(posts, narrated=True) != cache.cache_key_for(
            posts, narrated=False
        )


class TestStoreAndGet:
    def test_miss_before_store(self):
        assert cache.get("nope") is None

    def test_hit_after_store(self):
        cache.store("k", [{"type": "narrative", "text": "hi"}])
        assert cache.get("k") == [{"type": "narrative", "text": "hi"}]

    def test_expired_entry_returns_none(self, monkeypatch):
        cache.store("k", [{"type": "narrative", "text": "hi"}])
        # Fast-forward time past the TTL; capture the future value once so the
        # patched callable is not recursive.
        from app.chronicle.constants import CHRONICLE_CACHE_SECONDS

        future = time.time() + CHRONICLE_CACHE_SECONDS + 1
        monkeypatch.setattr("app.chronicle.cache.time.time", lambda: future)
        assert cache.get("k") is None

    def test_clear_empties_cache(self):
        cache.store("k", [{"type": "narrative", "text": "hi"}])
        cache.clear()
        assert cache.get("k") is None
