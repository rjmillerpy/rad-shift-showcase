"""
Tests for email verification system:
  - Signup requires email
  - Verification token generated and email sent
  - Verify endpoint marks user verified
  - Resend endpoint generates new token
  - Unverified users blocked from interactions (403)
  - Unverified users can still login and read feeds
  - Token expiry
  - Duplicate email rejection
"""

import time
from unittest.mock import patch

from app.auth.models import User


def _unverify(db_session, username):
    """Set a user back to unverified (undoing the auto-verify test hook)."""
    user = db_session.query(User).filter_by(username=username).first()
    if user:
        user.email_verified = False
        user.verification_token = user.verification_token or "test-token-" + username
        user.verification_token_expires = int(time.time()) + 86400
        db_session.commit()
        db_session.refresh(user)
    return user


def _signup(client, username, password="password123", email=...):
    return client.post(
        "/auth/signup",
        json={
            "username": username,
            "password": password,
            "email": f"{username}@test.com" if email is ... else email,
        },
    )


def _login(client, username, password="password123"):
    res = client.post("/auth/login", json={"username": username, "password": password})
    return res.json()


def _headers(login_data):
    return {"Authorization": f"Bearer {login_data['access_token']}"}


class TestSignupWithEmail:
    def test_signup_requires_email(self, client):
        res = client.post(
            "/auth/signup",
            json={
                "username": "no_email_user",
                "password": "password123",
            },
        )
        assert res.status_code == 400
        assert "email" in res.json()["detail"].lower()

    def test_signup_rejects_invalid_email(self, client):
        res = _signup(client, "bad_email", email="not-an-email")
        assert res.status_code == 400
        assert "email" in res.json()["detail"].lower()

    def test_signup_rejects_empty_email(self, client):
        res = _signup(client, "empty_email", email="")
        assert res.status_code == 400

    def test_signup_success_with_email(self, client):
        res = _signup(client, "email_user")
        assert res.status_code == 200
        assert (
            "verify" in res.json()["message"].lower()
            or "check your email" in res.json()["message"].lower()
        )

    def test_signup_rejects_duplicate_email(self, client):
        _signup(client, "dup_email1", email="shared@test.com")
        res = _signup(client, "dup_email2", email="shared@test.com")
        assert res.status_code == 400
        assert "email" in res.json()["detail"].lower()

    def test_login_returns_email_verified_false(self, client, db_session):
        _signup(client, "unverified_login")
        _unverify(db_session, "unverified_login")
        data = _login(client, "unverified_login")
        assert data["email_verified"] is False
        assert "access_token" in data


class TestVerifyEndpoint:
    def test_verify_with_valid_token(self, client, db_session):
        _signup(client, "verify_user")
        _unverify(db_session, "verify_user")
        from app.auth.models import User

        user = db_session.query(User).filter_by(username="verify_user").first()
        token = user.verification_token
        assert token is not None

        res = client.get(f"/auth/verify?token={token}")
        assert res.status_code == 200
        assert "verified" in res.json()["message"].lower()

        # User is now verified
        db_session.refresh(user)
        assert user.email_verified is True
        assert user.verification_token is None

    def test_verify_with_invalid_token(self, client):
        res = client.get("/auth/verify?token=bogus_token_123")
        assert res.status_code == 400
        assert "invalid" in res.json()["detail"].lower()

    def test_verify_already_verified(self, client, db_session):
        _signup(client, "already_verified")
        _unverify(db_session, "already_verified")
        from app.auth.models import User

        user = db_session.query(User).filter_by(username="already_verified").first()
        token = user.verification_token

        # Verify once
        client.get(f"/auth/verify?token={token}")

        # Try again with same token (now cleared)
        res = client.get(f"/auth/verify?token={token}")
        assert res.status_code == 400

    def test_verify_expired_token(self, client, db_session):
        _signup(client, "expired_verify")
        _unverify(db_session, "expired_verify")
        from app.auth.models import User

        user = db_session.query(User).filter_by(username="expired_verify").first()
        token = user.verification_token

        # Manually expire the token
        user.verification_token_expires = int(time.time()) - 1
        db_session.commit()

        res = client.get(f"/auth/verify?token={token}")
        assert res.status_code == 400
        assert "expired" in res.json()["detail"].lower()

    def test_verify_missing_token_param(self, client):
        res = client.get("/auth/verify")
        assert res.status_code == 422

    def test_login_returns_verified_true_after_verification(self, client, db_session):
        _signup(client, "post_verify")
        from app.auth.models import User

        user = db_session.query(User).filter_by(username="post_verify").first()
        client.get(f"/auth/verify?token={user.verification_token}")

        data = _login(client, "post_verify")
        assert data["email_verified"] is True


class TestResendVerification:
    def test_resend_for_unverified_user(self, client, db_session):
        _signup(client, "resend_user")
        _unverify(db_session, "resend_user")
        login_data = _login(client, "resend_user")
        headers = _headers(login_data)

        from app.auth.models import User

        user = db_session.query(User).filter_by(username="resend_user").first()
        old_token = user.verification_token

        res = client.post("/auth/resend-verification", headers=headers)
        assert res.status_code == 200
        assert "sent" in res.json()["message"].lower()

        db_session.refresh(user)
        assert user.verification_token != old_token  # New token generated

    def test_resend_for_already_verified_user(self, client, db_session):
        _signup(client, "verified_resend")
        from app.auth.models import User

        user = db_session.query(User).filter_by(username="verified_resend").first()
        client.get(f"/auth/verify?token={user.verification_token}")

        login_data = _login(client, "verified_resend")
        headers = _headers(login_data)

        res = client.post("/auth/resend-verification", headers=headers)
        assert res.status_code == 400
        assert "already verified" in res.json()["detail"].lower()

    def test_resend_requires_auth(self, client):
        res = client.post("/auth/resend-verification")
        assert res.status_code == 401


class TestVerificationGating:
    """Unverified users can login and read, but cannot interact."""

    def _create_unverified_user(self, client, db_session):
        _signup(client, "unv_gated")
        _unverify(db_session, "unv_gated")
        login_data = _login(client, "unv_gated")
        return _headers(login_data)

    def _create_verified_user(self, client, db_session, username="v_gated"):
        _signup(client, username)
        from app.auth.models import User

        user = db_session.query(User).filter_by(username=username).first()
        user.email_verified = True
        db_session.commit()
        login_data = _login(client, username)
        return _headers(login_data)

    def test_unverified_can_read_posts(self, client, db_session):
        headers = self._create_unverified_user(client, db_session)
        res = client.get("/posts/", headers=headers)
        assert res.status_code == 200

    def test_unverified_can_read_profile(self, client, db_session):
        headers = self._create_unverified_user(client, db_session)
        res = client.get("/profile/me", headers=headers)
        assert res.status_code == 200

    def test_unverified_cannot_create_post(self, client, db_session):
        headers = self._create_unverified_user(client, db_session)
        res = client.post(
            "/posts/add", data={"text": "test", "post_metadata": "{}"}, headers=headers
        )
        assert res.status_code == 403
        assert "verify" in res.json()["detail"].lower()

    def test_unverified_cannot_like(self, client, db_session):
        v_headers = self._create_verified_user(client, db_session, "like_poster")
        client.post(
            "/posts/add",
            data={"text": "Like me", "post_metadata": "{}", "is_draft": "false"},
            headers=v_headers,
        )
        pid = client.get("/posts/").json()["posts"][0]["id"]

        uv_headers = self._create_unverified_user(client, db_session)
        res = client.post(f"/posts/like/{pid}", headers=uv_headers)
        assert res.status_code == 403

    def test_unverified_cannot_laugh(self, client, db_session):
        v_headers = self._create_verified_user(client, db_session, "laugh_poster")
        client.post(
            "/posts/add",
            data={"text": "Laugh me", "post_metadata": "{}", "is_draft": "false"},
            headers=v_headers,
        )
        pid = client.get("/posts/").json()["posts"][0]["id"]

        uv_headers = self._create_unverified_user(client, db_session)
        res = client.post(f"/posts/laugh/{pid}", headers=uv_headers)
        assert res.status_code == 403

    def test_unverified_cannot_follow(self, client, db_session):
        _signup(client, "follow_target_v")
        uv_headers = self._create_unverified_user(client, db_session)
        res = client.post("/follow/follow_target_v", headers=uv_headers)
        assert res.status_code == 403

    def test_verified_user_can_interact(self, client, db_session):
        headers = self._create_verified_user(client, db_session, "interact_ok")
        res = client.post(
            "/posts/add",
            data={"text": "Verified post", "post_metadata": "{}", "is_draft": "false"},
            headers=headers,
        )
        assert res.status_code == 200


class TestEmailSending:
    """Verify email sending is called correctly."""

    def test_signup_calls_send_verification_email(self, client):
        # The global mock captures calls
        from unittest.mock import patch

        with patch("app.auth.service.send_verification_email") as mock_send:
            mock_send.return_value = True
            _signup(client, "send_test")
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][0] == "send_test@test.com"
            assert len(call_args[0][1]) > 20  # Token is long

    def test_resend_calls_send_verification_email(self, client, db_session):
        _signup(client, "resend_send")
        _unverify(db_session, "resend_send")
        login_data = _login(client, "resend_send")
        headers = _headers(login_data)

        with patch("app.auth.service.send_verification_email") as mock_send:
            mock_send.return_value = True
            client.post("/auth/resend-verification", headers=headers)
            mock_send.assert_called_once()
