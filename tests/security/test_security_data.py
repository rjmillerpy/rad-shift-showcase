"""Security tests: sensitive data exposure, CORS, response format."""

import json
import os

import pytest

from tests.security._helpers import _make_post, _setup


class TestSensitiveDataExposure:
    """Verify that API responses do not leak passwords, internal IDs, or private data."""

    def test_password_hash_not_in_profile_response(self, client):
        h = _setup(client, "hash_leak")
        res = client.get("/profile/me", headers=h)
        body = json.dumps(res.json())
        assert "password" not in body.lower()
        assert "$2b$" not in body  # bcrypt hash prefix

    def test_password_hash_not_in_public_profile(self, client):
        _setup(client, "pub_hash")
        res = client.get("/profile/pub_hash")
        body = json.dumps(res.json())
        assert "password" not in body.lower()
        assert "$2b$" not in body

    def test_password_hash_not_in_post_response(self, client):
        h = _setup(client, "post_hash")
        _make_post(client, h)
        res = client.get("/posts/", headers=h)
        body = json.dumps(res.json())
        assert "password" not in body.lower()
        assert "$2b$" not in body

    def test_jwt_secret_not_in_responses(self, client):
        h = _setup(client, "jwt_leak")
        for endpoint in ["/profile/me", "/posts/", "/posts/drafts", "/posts/saved"]:
            res = client.get(endpoint, headers=h)
            body = json.dumps(res.json())
            assert os.environ["JWT_SECRET"] not in body

    def test_database_url_not_in_error_responses(self, client):
        res = client.get("/profile/nonexistent_xyz")
        body = json.dumps(res.json())
        assert "postgresql" not in body.lower()
        assert "sqlite" not in body.lower()

    def test_internal_user_id_mapping_not_leaked_to_other_users(self, client):
        """Other users' posts shouldn't expose their user_id."""
        h_a = _setup(client, "id_leak_a")
        _make_post(client, h_a, text="A's post")

        h_b = _setup(client, "id_leak_b")
        res = client.get("/posts/", headers=h_b)
        post = next(p for p in res.json()["posts"] if p["text"] == "A's post")
        # Should not contain user_id field directly
        assert "user_id" not in post

    def test_error_messages_do_not_expose_stack_traces(self, client):
        """Error responses should not contain Python tracebacks."""
        res = client.post("/auth/login", json={"username": "x", "password": "y"})
        body = json.dumps(res.json())
        assert "Traceback" not in body
        assert 'File "' not in body


class TestCORSEnforcement:
    """CORS middleware should allow configured origins and block others."""

    def test_allowed_origin_gets_cors_headers(self, client):
        res = client.get("/posts/", headers={"Origin": "http://localhost:3000"})
        assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_disallowed_origin_blocked(self, client):
        res = client.get("/posts/", headers={"Origin": "http://evil.com"})
        allow = res.headers.get("access-control-allow-origin", "")
        assert "evil.com" not in allow

    def test_preflight_request_succeeds_for_allowed_origin(self, client):
        res = client.options(
            "/posts/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert res.status_code == 200
        assert "access-control-allow-origin" in res.headers

    def test_credentials_header_present(self, client):
        res = client.get("/posts/", headers={"Origin": "http://localhost:3000"})
        assert res.headers.get("access-control-allow-credentials") == "true"


class TestResponseFormatSafety:
    """Ensure API never returns HTML that could execute scripts."""

    @pytest.mark.parametrize(
        "path",
        [
            "/posts/",
            "/auth/protected",
            "/profile/nonexistent",
        ],
    )
    def test_responses_are_json_not_html(self, client, path):
        res = client.get(path)
        ct = res.headers.get("content-type", "")
        assert "application/json" in ct, f"{path} returned {ct} instead of JSON"
        assert "<html" not in res.text.lower()
