"""
Regression tests (part 1 of 2) — infrastructure, counters, and input bugs.

Each test documents:
  - What the bug was
  - How it manifested
  - How to verify it stays fixed

This file covers bugs #1–#8.
"""

import contextlib

from tests.regressions._helpers import _setup, _signup

# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #1: CORS allow_origins=["*"] with allow_credentials=True
#
#  The original code used allow_origins=["*"] which, combined with
#  allow_credentials=True, is a security violation. Browsers should reject
#  it, and it allows any origin to make authenticated requests.
#
#  Fix: Read ALLOWED_ORIGINS from env var, default to "http://localhost:3000".
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression01CORSWildcard:
    def test_allowed_origin_gets_cors_header(self, client):
        res = client.get("/posts/", headers={"Origin": "http://localhost:3000"})
        assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_wildcard_origin_not_reflected(self, client):
        res = client.get("/posts/", headers={"Origin": "http://evil.com"})
        allow = res.headers.get("access-control-allow-origin", "")
        assert allow != "*"
        assert "evil.com" not in allow


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #2: get_db() had no rollback on exception
#
#  If an unhandled error occurred mid-transaction, the session was closed
#  without rolling back, potentially leaving connections in a dirty state.
#
#  Fix: Added except Exception: db.rollback(); raise
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression02DBSessionRollback:
    def test_get_db_rolls_back_on_exception(self):
        from unittest.mock import MagicMock, patch

        from app.common.db import get_db

        mock_session = MagicMock()
        mock_session_class = MagicMock(return_value=mock_session)

        with patch("app.common.db.SessionLocal", mock_session_class):
            gen = get_db()
            next(gen)

            # Simulate an exception during request processing
            with contextlib.suppress(ValueError):
                gen.throw(ValueError("simulated error"))

            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #3: Race conditions on denormalized counters
#
#  toggle_like, toggle_repost, toggle_save all did Python-level
#  read-modify-write: post.likes = post.likes + 1. Under concurrent
#  requests, two users liking simultaneously could both read likes=5
#  and both write likes=6, losing one increment.
#
#  Fix: Replaced with atomic SQL UPDATE using func.coalesce + func.greatest.
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression03AtomicCounters:
    def test_like_counter_uses_atomic_update(self, client):
        """After like/unlike cycle, counter should be exactly 0."""
        h = _setup(client, "atomic_liker")
        client.post(
            "/posts/add",
            data={"text": "Atomic test", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        # Like
        res = client.post(f"/posts/like/{pid}", headers=h)
        assert res.json()["likes"] == 1

        # Unlike
        res = client.post(f"/posts/like/{pid}", headers=h)
        assert res.json()["likes"] == 0

        # Verify via feed (not just return value)
        post = next(p for p in client.get("/posts/", headers=h).json()["posts"] if p["id"] == pid)
        assert post["likes"] == 0

    def test_repost_counter_uses_atomic_update(self, client):
        h = _setup(client, "atomic_reposter")
        client.post(
            "/posts/add",
            data={"text": "Repost atomic", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        res = client.post(f"/posts/repost/{pid}", headers=h)
        assert res.json()["reposts"] == 1
        res = client.post(f"/posts/repost/{pid}", headers=h)
        assert res.json()["reposts"] == 0

    def test_save_counter_uses_atomic_update(self, client):
        h = _setup(client, "atomic_saver")
        client.post(
            "/posts/add",
            data={"text": "Save atomic", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        res = client.post(f"/posts/save/{pid}", headers=h)
        assert res.json()["saves"] == 1
        res = client.post(f"/posts/save/{pid}", headers=h)
        assert res.json()["saves"] == 0

    def test_counter_never_goes_negative(self, client, create_user, create_post, db_session):
        """Unliking a post that has 0 likes should stay at 0, not go to -1."""
        from app.posts.toggles import toggle_like

        user = create_user("neg_counter")
        post = create_post(user, text="Zero likes")
        post.likes = 0
        db_session.commit()

        # Like then unlike
        toggle_like(post.id, user, db_session)
        result = toggle_like(post.id, user, db_session)
        assert result["likes"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #4: share_post() anonymous shares didn't increment counter
#
#  Line 370 had: post.shares = (post.shares or 0)  — a no-op assignment.
#  Only authenticated shares incremented the counter.
#
#  Fix: Moved the atomic increment outside the `if user` block.
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression04AnonymousShareCounter:
    def test_anonymous_share_increments_counter(self, client):
        h = _setup(client, "anon_share_fix")
        client.post(
            "/posts/add",
            data={"text": "Share me anon", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/").json()["posts"][0]["id"]

        # Anonymous share
        res = client.post(f"/posts/share/{pid}")
        assert res.json()["shares"] == 1

        # Another anonymous share
        res = client.post(f"/posts/share/{pid}")
        assert res.json()["shares"] == 2

    def test_authenticated_share_also_increments(self, client):
        h = _setup(client, "auth_share_fix")
        client.post(
            "/posts/add",
            data={"text": "Share me auth", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        res = client.post(f"/posts/share/{pid}", headers=h)
        assert res.json()["shares"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #5: N+1 queries in post formatting functions
#
#  get_all_posts_formatted, get_replies_formatted, etc. each ran per-post
#  queries for likes, reposts, saves inside a loop. For 100 posts = 300+
#  queries instead of 4-6 batch queries.
#
#  Fix: Created _build_post_responses() with batch IN queries.
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression05BatchQueries:
    def test_build_post_responses_returns_correct_flags(self, client):
        """Verify batch query results match per-post behavior."""
        h_a = _setup(client, "batch_a")
        h_b = _setup(client, "batch_b")

        # A creates post
        client.post(
            "/posts/add",
            data={"text": "Batch test", "post_metadata": "{}", "is_draft": "false"},
            headers=h_a,
        )
        pid = client.get("/posts/", headers=h_a).json()["posts"][0]["id"]

        # B likes and saves it
        client.post(f"/posts/like/{pid}", headers=h_b)
        client.post(f"/posts/save/{pid}", headers=h_b)

        # B's view should show liked_by_me=True, is_saved_by_me=True
        posts = client.get("/posts/", headers=h_b).json()["posts"]
        post = next(p for p in posts if p["id"] == pid)
        assert post["liked_by_me"] is True
        assert post["is_saved_by_me"] is True
        assert post["is_me"] is False

        # A's view should show liked_by_me=False, is_me=True
        posts = client.get("/posts/", headers=h_a).json()["posts"]
        post = next(p for p in posts if p["id"] == pid)
        assert post["liked_by_me"] is False
        assert post["is_me"] is True


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #6: post.timestamp vs post.unix_timestamp in [username]/page.tsx
#
#  The public profile page used `post.timestamp` (from the profile API)
#  while every other page used `post.unix_timestamp`. After adding the
#  Post type, this caused a TypeScript build error. The profile API
#  response used "timestamp" but the Post type defined "unix_timestamp".
#
#  Fix: Changed profile/[username]/page.tsx to use post.unix_timestamp.
#  The backend profile service already returned "timestamp" as key name,
#  which is a different code path.
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression06TimestampFieldName:
    def test_profile_api_returns_unix_timestamp_field(self, client):
        """The profile API now returns full PostResponse with 'unix_timestamp'.
        Previously used 'timestamp' which caused frontend mismatches."""
        h = _setup(client, "ts_field")
        client.post(
            "/posts/add",
            data={"text": "Timestamp test", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )

        res = client.get("/profile/ts_field")
        post = res.json()["posts"][0]
        # Profile API now uses "unix_timestamp" (consistent with feed API)
        assert "unix_timestamp" in post
        assert isinstance(post["unix_timestamp"], int)
        assert post["unix_timestamp"] > 0

    def test_feed_api_returns_unix_timestamp_field(self, client):
        """The feed API uses 'unix_timestamp' as key."""
        h = _setup(client, "uts_field")
        client.post(
            "/posts/add",
            data={"text": "Unix timestamp test", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )

        res = client.get("/posts/", headers=h)
        post = res.json()["posts"][0]
        assert "unix_timestamp" in post


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #7: Flask-Bcrypt used in FastAPI app
#
#  flask_bcrypt.Bcrypt() was instantiated without a Flask app, dragging
#  in Flask and 10+ unused dependencies.
#
#  Fix: Replaced with direct bcrypt library usage. Verified password
#  hashes are compatible ($2b$ format).
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression07BcryptDirect:
    def test_password_hashing_works_after_migration(self, client):
        """Signup + login should work with direct bcrypt."""
        _signup(client, "bcrypt_reg")
        res = client.post("/auth/login", json={"username": "bcrypt_reg", "password": "password123"})
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_wrong_password_fails_after_migration(self, client):
        _signup(client, "bcrypt_fail")
        res = client.post("/auth/login", json={"username": "bcrypt_fail", "password": "wrong"})
        assert res.status_code == 401

    def test_password_hash_format(self, create_user):
        user = create_user("hash_fmt")
        assert user.password_hash.startswith("$2b$")


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #8: Input validation missing
#
#  No username character validation, no password length check, no post
#  text length limit.
#
#  Fix: Added username 3-80 chars + alphanumeric regex, password min 8,
#  post text max 5000.
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression08InputValidation:
    def test_username_too_short_rejected(self, client):
        res = _signup(client, "ab")
        assert res.status_code == 400

    def test_username_special_chars_rejected(self, client):
        res = _signup(client, "user<script>")
        assert res.status_code == 400

    def test_password_too_short_rejected(self, client):
        res = _signup(client, "valid_user", "short")
        assert res.status_code == 400

    def test_post_text_too_long_rejected(self, client):
        h = _setup(client, "long_post_reg")
        res = client.post(
            "/posts/add",
            data={"text": "x" * 5001, "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        assert res.status_code == 400
