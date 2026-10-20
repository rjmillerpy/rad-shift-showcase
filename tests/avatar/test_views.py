"""Tests for app/avatar/views.py — avatar API endpoints.

The cross-cutting signup→avatar flow lives in tests/integration/test_signup_avatar.py.
"""

import pytest

from app.avatar.constants import MAX_PREVIEW_EMAIL_LEN, MAX_PREVIEW_USERNAME_LEN


class TestPreviewAvatar:
    def test_preview_returns_png(self, client):
        resp = client.get("/avatar/preview?username=test&email=t@t.com")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_preview_deterministic(self, client):
        r1 = client.get("/avatar/preview?username=alice&email=a@t.com")
        r2 = client.get("/avatar/preview?username=alice&email=a@t.com")
        assert r1.content == r2.content

    def test_preview_different_users_produce_different_output(self, client):
        r1 = client.get("/avatar/preview?username=alice&email=a@t.com")
        r2 = client.get("/avatar/preview?username=bob&email=b@t.com")
        assert r1.content != r2.content

    @pytest.mark.parametrize(
        "params",
        [
            {"email": "a@t.com"},
            {"username": "alice"},
            {"username": "", "email": "a@t.com"},
            {"username": "alice", "email": ""},
            {"username": "x" * (MAX_PREVIEW_USERNAME_LEN + 1), "email": "a@t.com"},
            {"username": "alice", "email": "x" * (MAX_PREVIEW_EMAIL_LEN + 1)},
        ],
        ids=[
            "missing_username",
            "missing_email",
            "empty_username",
            "empty_email",
            "username_too_long",
            "email_too_long",
        ],
    )
    def test_preview_rejects_invalid_params(self, client, params):
        resp = client.get("/avatar/preview", params=params)
        assert resp.status_code == 422


class TestRegenerateAvatar:
    def test_regenerate_requires_auth(self, client):
        resp = client.post("/avatar/regenerate")
        assert resp.status_code in (401, 422)

    def test_regenerate_returns_url(self, client, create_user, auth_header):
        create_user(username="regen_user")
        resp = client.post("/avatar/regenerate", headers=auth_header("regen_user"))
        assert resp.status_code == 200
        assert "url" in resp.json()

    def test_regenerate_persists_url_on_user(
        self,
        client,
        create_user,
        auth_header,
        db_session,
    ):
        user = create_user(username="regen_persist")
        old_url = user.profile_picture_url
        resp = client.post("/avatar/regenerate", headers=auth_header("regen_persist"))
        assert resp.status_code == 200
        db_session.refresh(user)
        assert user.profile_picture_url == resp.json()["url"]
        assert user.profile_picture_url != old_url or old_url is None

    def test_regenerate_404_when_jwt_user_gone(
        self,
        client,
        auth_header,
        db_session,
    ):
        """JWT names a user who has since been deleted → 404."""
        from app.auth.models import User

        transient = User(
            username="regen_transient",
            email="regen_transient@test.com",
            email_verified=True,
        )
        transient.set_password("password123")
        db_session.add(transient)
        db_session.commit()
        headers = auth_header("regen_transient")
        db_session.delete(transient)
        db_session.commit()

        resp = client.post("/avatar/regenerate", headers=headers)
        assert resp.status_code == 404
