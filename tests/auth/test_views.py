"""Tests for app/auth – signup, login, protected endpoint."""

import pytest


class TestSignup:
    def test_signup_success(self, client):
        resp = client.post(
            "/auth/signup",
            json={"username": "alice", "password": "securepass1", "email": "alice@test.com"},
        )
        assert resp.status_code == 200
        assert "User created successfully" in resp.json()["message"]

    def test_signup_duplicate_user(self, client, create_user):
        create_user(username="alice", password="securepass1")
        resp = client.post(
            "/auth/signup",
            json={"username": "alice", "password": "securepass1", "email": "alice2@test.com"},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    @pytest.mark.parametrize(
        "username,password,email,expected_status,expected_fragment",
        [
            ("ab", "securepass1", "ab@test.com", 400, "3 and 80"),
            ("", "securepass1", "empty@test.com", 400, "3 and 80"),
            ("a" * 81, "securepass1", "long@test.com", 400, "3 and 80"),
            ("valid_user", "short", "valid@test.com", 400, "8 characters"),
            ("inv@lid!", "securepass1", "inv@test.com", 400, ""),  # invalid chars
        ],
        ids=[
            "short-username",
            "empty-username",
            "long-username",
            "short-password",
            "invalid-chars",
        ],
    )
    def test_signup_validation(
        self, client, username, password, email, expected_status, expected_fragment
    ):
        resp = client.post(
            "/auth/signup", json={"username": username, "password": password, "email": email}
        )
        assert resp.status_code == expected_status
        if expected_fragment:
            assert expected_fragment in resp.json()["detail"]


class TestLogin:
    def test_login_success(self, client, create_user):
        create_user(username="alice", password="securepass1")
        resp = client.post("/auth/login", json={"username": "alice", "password": "securepass1"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client, create_user):
        create_user(username="alice", password="securepass1")
        resp = client.post("/auth/login", json={"username": "alice", "password": "wrongpass1"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_login_nonexistent_user(self, client):
        resp = client.post("/auth/login", json={"username": "ghost", "password": "whatever1"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"


class TestProtected:
    def test_protected_with_token(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.get("/auth/protected", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert "alice" in resp.json()["message"]

    def test_protected_without_token(self, client):
        resp = client.get("/auth/protected")
        assert resp.status_code in (401, 422)


class TestPromoteAdmin:
    def test_503_when_admin_secret_not_configured(
        self,
        client,
        create_user,
        auth_header,
        monkeypatch,
    ):
        monkeypatch.delenv("ADMIN_SECRET", raising=False)
        create_user(username="alice")
        resp = client.post(
            "/auth/promote-admin",
            json={"secret": "anything"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 503

    def test_403_on_wrong_secret(self, client, create_user, auth_header, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "correct-secret")
        create_user(username="alice")
        resp = client.post(
            "/auth/promote-admin",
            json={"secret": "wrong-secret"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 403

    def test_promotes_current_user_on_correct_secret(
        self,
        client,
        create_user,
        auth_header,
        monkeypatch,
        db_session,
    ):
        monkeypatch.setenv("ADMIN_SECRET", "the-key")
        user = create_user(username="alice")
        resp = client.post(
            "/auth/promote-admin",
            json={"secret": "the-key"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200
        db_session.refresh(user)
        assert user.is_admin is True

    def test_401_without_token(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "the-key")
        resp = client.post("/auth/promote-admin", json={"secret": "the-key"})
        assert resp.status_code in (401, 422)

    def test_422_when_body_missing_secret(self, client, create_user, auth_header, monkeypatch):
        """PromoteAdminRequest requires `secret` — empty body is a validation error."""
        monkeypatch.setenv("ADMIN_SECRET", "the-key")
        create_user(username="alice")
        resp = client.post(
            "/auth/promote-admin",
            json={},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 422

    def test_404_when_jwt_user_no_longer_exists(
        self,
        client,
        auth_header,
        monkeypatch,
        db_session,
    ):
        """JWT names a user that has since been deleted — endpoint returns 404."""
        from app.auth.models import User

        monkeypatch.setenv("ADMIN_SECRET", "the-key")
        # Mint a token for a user, then delete that user before the request.
        transient = User(username="transient", email="t@test.com", email_verified=True)
        transient.set_password("password123")
        db_session.add(transient)
        db_session.commit()
        headers = auth_header("transient")
        db_session.delete(transient)
        db_session.commit()

        resp = client.post(
            "/auth/promote-admin",
            json={"secret": "the-key"},
            headers=headers,
        )
        assert resp.status_code == 404
