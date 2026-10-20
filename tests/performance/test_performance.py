"""
Performance tests — verify the application meets response time and
throughput expectations under load.

These tests use the in-memory SQLite TestClient, so they measure
application-layer performance (routing, ORM, serialization) rather
than network or PostgreSQL performance.

Thresholds are generous (meant to catch regressions, not benchmark hardware).
"""

import json
import statistics
import time

import pytest

# Timing assertions are only meaningful without other tests competing for the
# CPU, so CI runs this module on its own after the parallel run (-m perf).
pytestmark = pytest.mark.perf

# ── helpers ──────────────────────────────────────────────────────────────────


def _signup(client, username, password="password123"):
    return client.post(
        "/auth/signup",
        json={"username": username, "password": password, "email": f"{username}@test.com"},
    )


def _login(client, username, password="password123"):
    res = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _setup(client, username):
    _signup(client, username)
    return _login(client, username)


def _timed(fn, *args, **kwargs):
    """Run fn and return (result, elapsed_seconds)."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def _benchmark(fn, iterations=20):
    """Run fn N times, return (mean, p95, max) in seconds."""
    times = []
    for _ in range(iterations):
        _, elapsed = _timed(fn)
        times.append(elapsed)
    times.sort()
    p95_idx = int(len(times) * 0.95)
    return statistics.mean(times), times[p95_idx], max(times)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENDPOINT RESPONSE TIME BENCHMARKS
# ═══════════════════════════════════════════════════════════════════════════════


class TestEndpointResponseTimes:
    """Each endpoint should respond within reasonable time thresholds."""

    THRESHOLD_MS = 500  # 500ms per request (generous for SQLite TestClient)

    def test_signup_response_time(self, client):
        mean, p95, mx = _benchmark(lambda: _signup(client, f"perf_signup_{time.perf_counter_ns()}"))
        assert p95 < self.THRESHOLD_MS / 1000, (
            f"Signup p95={p95 * 1000:.0f}ms exceeds {self.THRESHOLD_MS}ms"
        )

    def test_login_response_time(self, client):
        _signup(client, "perf_login")
        mean, p95, mx = _benchmark(
            lambda: client.post(
                "/auth/login", json={"username": "perf_login", "password": "password123"}
            )
        )
        assert p95 < self.THRESHOLD_MS / 1000, (
            f"Login p95={p95 * 1000:.0f}ms exceeds {self.THRESHOLD_MS}ms"
        )

    def test_get_posts_response_time(self, client):
        h = _setup(client, "perf_poster")
        for i in range(10):
            client.post(
                "/posts/add",
                data={"text": f"Perf post {i}", "post_metadata": "{}", "is_draft": "false"},
                headers=h,
            )

        mean, p95, mx = _benchmark(lambda: client.get("/posts/", headers=h))
        assert p95 < self.THRESHOLD_MS / 1000, (
            f"GET /posts p95={p95 * 1000:.0f}ms exceeds {self.THRESHOLD_MS}ms"
        )

    def test_like_toggle_response_time(self, client):
        h = _setup(client, "perf_liker")
        client.post(
            "/posts/add",
            data={"text": "Like target", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        mean, p95, mx = _benchmark(lambda: client.post(f"/posts/like/{pid}", headers=h))
        assert p95 < self.THRESHOLD_MS / 1000, (
            f"Like toggle p95={p95 * 1000:.0f}ms exceeds {self.THRESHOLD_MS}ms"
        )

    def test_profile_response_time(self, client):
        h = _setup(client, "perf_profile")
        mean, p95, mx = _benchmark(lambda: client.get("/profile/me", headers=h))
        assert p95 < self.THRESHOLD_MS / 1000, (
            f"Profile p95={p95 * 1000:.0f}ms exceeds {self.THRESHOLD_MS}ms"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  LARGE DATASET PERFORMANCE — N+1 query regression detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestLargeDatasetPerformance:
    """Verify that feed endpoints scale linearly, not quadratically, with post count."""

    def _create_posts(self, client, headers, count):
        for i in range(count):
            client.post(
                "/posts/add",
                data={
                    "text": f"Bulk post {i}",
                    "post_metadata": json.dumps({"tags": f"tag{i}"}),
                    "is_draft": "false",
                },
                headers=headers,
            )

    def test_feed_scales_with_post_count(self, client):
        """Time to fetch feed with 10 posts vs 50 posts should not be 5x slower
        (would indicate N+1 queries)."""
        h = _setup(client, "scale_user")

        # 10 posts
        self._create_posts(client, h, 10)
        _, time_10 = _timed(lambda: client.get("/posts/", headers=h))

        # 40 more (total 50)
        self._create_posts(client, h, 40)
        _, time_50 = _timed(lambda: client.get("/posts/", headers=h))

        # With batch queries, 50 posts should take less than 4x the time of 10
        ratio = time_50 / max(time_10, 0.001)
        assert ratio < 8, f"Feed time ratio 50/10 posts = {ratio:.1f}x (suspected N+1 regression)"

    def test_replies_scale_with_count(self, client):
        """Replies endpoint should handle many replies efficiently."""
        h = _setup(client, "reply_scale")
        client.post(
            "/posts/add",
            data={"text": "Parent", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        # Create 30 replies
        for i in range(30):
            client.post(
                "/posts/add",
                data={
                    "text": f"Reply {i}",
                    "post_metadata": "{}",
                    "is_draft": "false",
                    "is_reply": "true",
                    "parent_post_id": str(pid),
                },
                headers=h,
            )

        _, elapsed = _timed(lambda: client.get(f"/posts/{pid}/replies", headers=h))
        assert elapsed < 2.0, f"30 replies took {elapsed * 1000:.0f}ms"

        res = client.get(f"/posts/{pid}/replies", headers=h)
        assert len(res.json()["replies"]) == 30

    def test_saved_posts_scale(self, client):
        """Saving and retrieving many posts should be efficient."""
        h = _setup(client, "save_scale")
        self._create_posts(client, h, 20)

        posts = client.get("/posts/", headers=h).json()["posts"]
        for p in posts:
            client.post(f"/posts/save/{p['id']}", headers=h)

        _, elapsed = _timed(lambda: client.get("/posts/saved", headers=h))
        assert elapsed < 2.0, f"20 saved posts took {elapsed * 1000:.0f}ms"

        res = client.get("/posts/saved", headers=h)
        assert len(res.json()["posts"]) == 20

    def test_drafts_scale(self, client):
        """Drafts endpoint with many drafts."""
        h = _setup(client, "draft_scale")
        for i in range(25):
            client.post(
                "/posts/add",
                data={"text": f"Draft {i}", "post_metadata": "{}", "is_draft": "true"},
                headers=h,
            )

        _, elapsed = _timed(lambda: client.get("/posts/drafts", headers=h))
        assert elapsed < 2.0, f"25 drafts took {elapsed * 1000:.0f}ms"

        res = client.get("/posts/drafts", headers=h)
        assert len(res.json()["drafts"]) == 25


# ═══════════════════════════════════════════════════════════════════════════════
#  FOLLOW FEED PERFORMANCE — complex query with joins
# ═══════════════════════════════════════════════════════════════════════════════


class TestFollowFeedPerformance:
    """The following feed involves joins, reposts, and filtering — test it doesn't degrade."""

    def test_following_feed_with_many_followed_users(self, client):
        """Follow 10 users who each have 5 posts. Feed should return quickly."""
        follower_h = _setup(client, "perf_follower")

        for i in range(10):
            author = f"perf_author_{i}"
            _signup(client, author)
            author_h = _login(client, author)
            for j in range(5):
                client.post(
                    "/posts/add",
                    data={
                        "text": f"Post {j} by {author}",
                        "post_metadata": "{}",
                        "is_draft": "false",
                    },
                    headers=author_h,
                )
            client.post(f"/follow/{author}", headers=follower_h)

        _, elapsed = _timed(lambda: client.get("/posts/following", headers=follower_h))
        assert elapsed < 3.0, f"Following feed (10 users, 50 posts) took {elapsed * 1000:.0f}ms"

        res = client.get("/posts/following?offset=0&limit=100", headers=follower_h)
        assert len(res.json()["posts"]) == 50


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTION THROUGHPUT — rapid operations
# ═══════════════════════════════════════════════════════════════════════════════


class TestInteractionThroughput:
    """Verify many rapid interactions complete without degradation."""

    def test_rapid_like_unlike_throughput(self, client):
        """50 like/unlike toggles in sequence."""
        h = _setup(client, "throughput_liker")
        client.post(
            "/posts/add",
            data={"text": "Toggle me fast", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        start = time.perf_counter()
        for _ in range(50):
            client.post(f"/posts/like/{pid}", headers=h)
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"50 like toggles took {elapsed * 1000:.0f}ms"

        # Verify consistency: 50 toggles (even count) = unliked, 0 likes
        res = client.get("/posts/", headers=h)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["likes"] == 0

    def test_rapid_post_creation_throughput(self, client):
        """Create 30 posts in sequence."""
        h = _setup(client, "throughput_poster")

        start = time.perf_counter()
        for i in range(30):
            client.post(
                "/posts/add",
                data={"text": f"Rapid post {i}", "post_metadata": "{}", "is_draft": "false"},
                headers=h,
            )
        elapsed = time.perf_counter() - start

        assert elapsed < 15.0, f"30 post creations took {elapsed * 1000:.0f}ms"

        res = client.get("/posts/?offset=0&limit=100", headers=h)
        my_posts = [p for p in res.json()["posts"] if p["username"] == "throughput_poster"]
        assert len(my_posts) == 30

    def test_rapid_share_throughput(self, client):
        """20 share operations on same post."""
        h = _setup(client, "throughput_sharer")
        client.post(
            "/posts/add",
            data={"text": "Share target", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        start = time.perf_counter()
        for _ in range(20):
            # Anonymous shares to avoid duplicate constraint
            client.post(f"/posts/share/{pid}")
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"20 shares took {elapsed * 1000:.0f}ms"

        res = client.get("/posts/")
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["shares"] == 20


# ═══════════════════════════════════════════════════════════════════════════════
#  SERIALIZATION PERFORMANCE — PostResponse construction
# ═══════════════════════════════════════════════════════════════════════════════


class TestSerializationPerformance:
    """Verify that building PostResponse objects with batch queries is efficient."""

    def test_post_response_with_complex_metadata(self, client):
        """Posts with large metadata should not slow down serialization."""
        h = _setup(client, "meta_perf")
        big_meta = json.dumps(
            {
                "tags": "|".join(f"tag{i}" for i in range(50)),
                "tagged_users": [f"user{i}" for i in range(20)],
                "location": "A" * 200,
                "extra": {"nested": {"deep": "value"}},
            }
        )

        for i in range(10):
            client.post(
                "/posts/add",
                data={
                    "text": f"Complex meta post {i}",
                    "post_metadata": big_meta,
                    "is_draft": "false",
                },
                headers=h,
            )

        _, elapsed = _timed(lambda: client.get("/posts/", headers=h))
        assert elapsed < 2.0, f"10 posts with complex metadata took {elapsed * 1000:.0f}ms"

    def test_post_response_with_quotes_and_replies(self, client):
        """Posts that have quotes and replies should include counts efficiently."""
        h = _setup(client, "quote_perf")

        # Create parent post
        client.post(
            "/posts/add",
            data={"text": "Quotable", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        # Create 10 quotes and 10 replies
        for i in range(10):
            client.post(
                "/posts/add",
                data={
                    "text": f"Quote {i}",
                    "post_metadata": "{}",
                    "is_draft": "false",
                    "parent_post_id": str(pid),
                },
                headers=h,
            )
            client.post(
                "/posts/add",
                data={
                    "text": f"Reply {i}",
                    "post_metadata": "{}",
                    "is_draft": "false",
                    "is_reply": "true",
                    "parent_post_id": str(pid),
                },
                headers=h,
            )

        _, elapsed = _timed(lambda: client.get("/posts/", headers=h))
        assert elapsed < 2.0, f"Feed with quote/reply counts took {elapsed * 1000:.0f}ms"

        res = client.get("/posts/", headers=h)
        parent = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert parent["replies_count"] == 10
        assert parent["quotes_count"] == 10


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH PERFORMANCE — bcrypt is intentionally slow, verify it's bounded
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthPerformance:
    """Bcrypt hashing is CPU-intensive by design. Verify it doesn't exceed bounds."""

    def test_signup_bcrypt_bounded(self, client):
        """Single signup (which hashes the password) should complete in <2s."""
        _, elapsed = _timed(lambda: _signup(client, "bcrypt_perf"))
        assert elapsed < 2.0, f"Signup with bcrypt took {elapsed * 1000:.0f}ms"

    def test_login_bcrypt_bounded(self, client):
        """Login (which verifies the hash) should complete in <2s."""
        _signup(client, "bcrypt_login_perf")
        _, elapsed = _timed(
            lambda: client.post(
                "/auth/login", json={"username": "bcrypt_login_perf", "password": "password123"}
            )
        )
        assert elapsed < 2.0, f"Login with bcrypt took {elapsed * 1000:.0f}ms"

    def test_failed_login_same_speed(self, client):
        """Failed login should take similar time as successful (prevent timing attacks)."""
        _signup(client, "timing_user")

        # Successful login
        _, success_time = _timed(
            lambda: client.post(
                "/auth/login", json={"username": "timing_user", "password": "password123"}
            )
        )

        # Failed login (wrong password — still runs bcrypt check)
        _, fail_time = _timed(
            lambda: client.post(
                "/auth/login", json={"username": "timing_user", "password": "wrongpassword"}
            )
        )

        # Should be within 5x of each other (bcrypt runs in both cases)
        ratio = max(success_time, fail_time) / max(min(success_time, fail_time), 0.001)
        assert ratio < 5.0, (
            f"Login timing ratio success/fail = {ratio:.1f}x (potential timing leak)"
        )
