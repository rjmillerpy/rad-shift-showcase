"""API contract tests for /auth endpoints (signup, login, protected)."""

import pytest

from tests.helpers import setup_user, signup


class TestAuthAPI:
    """POST /auth/signup, POST /auth/login, GET /auth/protected"""

    # ── /auth/signup ─────────────────────────────────────────────────────

    def test_signup_response_schema(self, client):
        res = signup(client, "schema_user")
        assert res.status_code == 200
        body = res.json()
        assert "message" in body
        assert "User created successfully" in body["message"]
        assert res.headers["content-type"] == "application/json"

    def test_signup_missing_username(self, client):
        res = client.post("/auth/signup", json={"password": "password123"})
        assert res.status_code == 422  # Pydantic validation
        body = res.json()
        assert "detail" in body

    def test_signup_missing_password(self, client):
        res = client.post("/auth/signup", json={"username": "nopass"})
        assert res.status_code == 422

    def test_signup_empty_body(self, client):
        res = client.post("/auth/signup", json={})
        assert res.status_code == 422

    def test_signup_wrong_content_type(self, client):
        res = client.post(
            "/auth/signup", content="not json", headers={"content-type": "text/plain"}
        )
        assert res.status_code == 422

    @pytest.mark.parametrize(
        "username,password,expected_status",
        [
            ("abc", "password123", 200),
            ("ab", "password123", 400),
            ("a" * 80, "password123", 200),
            ("a" * 81, "password123", 400),
            ("pw_test1", "12345678", 200),
            ("pw_test2", "1234567", 400),
        ],
        ids=[
            "username-min-valid",
            "username-below-min",
            "username-max-valid",
            "username-above-max",
            "password-min-valid",
            "password-below-min",
        ],
    )
    def test_signup_boundary(self, client, username, password, expected_status):
        res = signup(client, username, password)
        assert res.status_code == expected_status

    def test_signup_duplicate_returns_400(self, client):
        signup(client, "dup_api")
        res = signup(client, "dup_api")
        assert res.status_code == 400
        assert "already exists" in res.json()["detail"]

    # ── /auth/login ──────────────────────────────────────────────────────

    def test_login_response_schema(self, client):
        signup(client, "login_schema")
        res = client.post(
            "/auth/login", json={"username": "login_schema", "password": "password123"}
        )
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body
        assert isinstance(body["access_token"], str)
        assert len(body["access_token"]) > 20  # JWT is long

    def test_login_wrong_password_returns_401(self, client):
        signup(client, "login_fail")
        res = client.post("/auth/login", json={"username": "login_fail", "password": "wrong"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid credentials"

    def test_login_nonexistent_user_returns_401(self, client):
        res = client.post("/auth/login", json={"username": "ghost", "password": "password123"})
        assert res.status_code == 401

    def test_login_missing_fields_returns_422(self, client):
        res = client.post("/auth/login", json={"username": "only_user"})
        assert res.status_code == 422

    # ── /auth/protected ──────────────────────────────────────────────────

    def test_protected_with_valid_token(self, client):
        headers = setup_user(client, "protected_user")
        res = client.get("/auth/protected", headers=headers)
        assert res.status_code == 200
        assert "protected_user" in res.json()["message"]

    def test_protected_without_token_returns_401(self, client):
        res = client.get("/auth/protected")
        assert res.status_code == 401

    def test_protected_with_invalid_token(self, client):
        res = client.get("/auth/protected", headers={"Authorization": "Bearer invalid.token.here"})
        assert res.status_code in (401, 422)

    def test_protected_with_malformed_header(self, client):
        res = client.get("/auth/protected", headers={"Authorization": "NotBearer token"})
        assert res.status_code in (401, 422)
