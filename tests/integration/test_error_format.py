"""API contract tests for cross-cutting concerns (error format, CORS)."""

from tests.helpers import signup


class TestErrorFormat:
    """All error responses should have a consistent {detail: ...} shape."""

    def test_401_has_detail(self, client):
        res = client.get("/auth/protected")
        assert "detail" in res.json()

    def test_400_has_detail(self, client):
        signup(client, "err_user")
        res = signup(client, "err_user")
        assert "detail" in res.json()

    def test_404_has_detail(self, client):
        res = client.get("/profile/nonexistent_12345")
        assert "detail" in res.json()

    def test_422_has_detail(self, client):
        res = client.post("/auth/signup", json={})
        assert "detail" in res.json()

    def test_all_errors_return_json(self, client):
        """Verify error responses are always JSON, not HTML."""
        res = client.get("/auth/protected")
        assert "application/json" in res.headers["content-type"]

        res = client.get("/profile/nonexistent_12345")
        assert "application/json" in res.headers["content-type"]


class TestCORS:
    """Verify CORS middleware is active."""

    def test_cors_allows_configured_origin(self, client):
        res = client.options(
            "/posts/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORSMiddleware should respond to preflight
        assert res.status_code == 200
        assert "access-control-allow-origin" in res.headers

    def test_cors_rejects_unconfigured_origin(self, client):
        res = client.options(
            "/posts/",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should not include the evil origin in allow-origin
        allow = res.headers.get("access-control-allow-origin", "")
        assert "evil.com" not in allow
