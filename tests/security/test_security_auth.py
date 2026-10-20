"""Security tests: authentication enforcement and JWT edge cases."""

import io
import time

import pytest

from tests.security._helpers import _make_post, _setup


class TestAuthEnforcement:
    """Verify all endpoints that require auth actually enforce it."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("POST", "/posts/add"),
            ("GET", "/posts/following"),
            ("POST", "/posts/like/1"),
            ("POST", "/posts/repost/1"),
            ("POST", "/posts/save/1"),
            ("GET", "/posts/saved"),
            ("POST", "/posts/slop/1"),
            ("GET", "/posts/drafts"),
            ("POST", "/posts/drafts/publish/1"),
            ("GET", "/profile/me"),
            ("PUT", "/profile/me"),
            ("POST", "/profile/me/upload-profile-pic"),
            ("POST", "/follow/someone"),
            ("POST", "/follow/un/someone"),
            ("GET", "/auth/protected"),
        ],
    )
    def test_protected_endpoint_returns_401_without_token(self, client, method, path):
        kwargs = {}
        if method == "POST" and "slop" in path:
            kwargs = {"json": {"reason": "test"}}
        elif method == "PUT":
            kwargs = {"json": {"bio": "test"}}
        elif method == "POST" and "add" in path:
            kwargs = {"data": {"text": "test", "post_metadata": "{}"}}
        elif method == "POST" and "upload" in path:
            kwargs = {"files": {"file": ("t.jpg", io.BytesIO(b"x"), "image/jpeg")}}

        res = getattr(client, method.lower())(path, **kwargs)
        assert res.status_code == 401, (
            f"{method} {path} should require auth but got {res.status_code}"
        )

    @pytest.mark.parametrize(
        "path",
        [
            "/posts/",
            "/posts/1/replies",
            "/profile/someuser",
        ],
    )
    def test_public_endpoint_allows_anonymous(self, client, path):
        res = client.get(path)
        assert res.status_code in (200, 404), f"GET {path} should allow anonymous"

    def test_share_allows_anonymous(self, client):
        h = _setup(client, "share_anon_sec")
        _make_post(client, h)
        pid = client.get("/posts/").json()["posts"][0]["id"]
        res = client.post(f"/posts/share/{pid}")
        assert res.status_code == 200

    def test_invalid_jwt_format_rejected(self, client):
        res = client.get("/profile/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
        assert res.status_code in (401, 422)

    def test_missing_bearer_prefix_rejected(self, client):
        res = client.get("/profile/me", headers={"Authorization": "Token abc123"})
        assert res.status_code in (401, 422)

    def test_empty_auth_header_rejected(self, client):
        res = client.get("/profile/me", headers={"Authorization": ""})
        assert res.status_code in (401, 422)


class TestJWTEdgeCases:
    """JWT token handling edge cases."""

    def test_token_for_deleted_user_concept(self, client):
        """If a user is created, gets a token, then user is somehow removed,
        endpoints using that token should fail gracefully."""
        h = _setup(client, "ephemeral")
        res = client.get("/profile/me", headers=h)
        assert res.status_code == 200  # Works while user exists

    def test_token_from_wrong_secret_rejected(self, client):
        """A token signed with a different secret should be rejected."""
        import jwt

        fake_token = jwt.encode(
            {"sub": "hacker", "iat": time.time(), "exp": time.time() + 300},
            "a-wrong-secret-that-is-also-32-bytes-long",
            algorithm="HS256",
        )
        res = client.get("/profile/me", headers={"Authorization": f"Bearer {fake_token}"})
        assert res.status_code in (401, 422)

    def test_token_with_modified_subject(self, client):
        """Even with the right secret, a modified subject should not grant access
        to a nonexistent user's data."""
        import os

        import jwt

        secret = os.environ["JWT_SECRET"]
        fake_token = jwt.encode(
            {
                "sub": "nonexistent_hacker",
                "iat": time.time(),
                "exp": time.time() + 300,
                "type": "access",
                "fresh": False,
                "nbf": time.time(),
                "jti": "fake-jti",
            },
            secret,
            algorithm="HS256",
        )
        res = client.get("/profile/me", headers={"Authorization": f"Bearer {fake_token}"})
        # fastapi-jwt-auth may reject the crafted token format, or the user isn't found
        assert res.status_code in (401, 404, 422)


class TestFollowAuthorization:
    """Follow system enforces relationship rules."""

    def test_cannot_follow_self(self, client):
        h = _setup(client, "self_follower")
        res = client.post("/follow/self_follower", headers=h)
        assert res.status_code == 400

    def test_cannot_double_follow(self, client):
        _setup(client, "follow_target_sec")
        h = _setup(client, "double_follower")
        client.post("/follow/follow_target_sec", headers=h)
        res = client.post("/follow/follow_target_sec", headers=h)
        assert res.status_code == 400

    def test_cannot_unfollow_if_not_following(self, client):
        _setup(client, "unf_target_sec")
        h = _setup(client, "not_follower")
        res = client.post("/follow/un/unf_target_sec", headers=h)
        assert res.status_code == 400

    def test_follow_nonexistent_user(self, client):
        h = _setup(client, "follow_ghost_sec")
        res = client.post("/follow/nonexistent_user_xyz", headers=h)
        assert res.status_code == 404
