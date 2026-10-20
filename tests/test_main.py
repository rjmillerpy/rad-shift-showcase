"""Tests for the main app factory and top-level configuration."""

from unittest.mock import MagicMock, patch

import pytest

_ALL_PREFIXES = [
    "/auth",
    "/profile",
    "/posts",
    "/follow",
    "/blog",
    "/avatar",
    "/amble/avatar",
    "/amble/content",
    "/widgets",
    "/generators",
    "/trends",
    "/health",
]


class TestAppRoutes:
    @pytest.mark.parametrize("prefix", _ALL_PREFIXES, ids=_ALL_PREFIXES)
    def test_every_expected_prefix_registered(self, client, prefix):
        # The OpenAPI schema is the public list of registered paths; app.routes
        # holds framework-internal wrapper objects that vary between versions.
        paths = client.app.openapi()["paths"]
        assert any(p.startswith(prefix) for p in paths), f"Missing route prefix: {prefix}"

    def test_router_count_matches_manifest(self):
        """The `_ROUTERS` manifest and `_ALL_PREFIXES` in the tests must stay in sync."""
        from app.main import _ROUTERS

        registered = {prefix for _, prefix in _ROUTERS}
        assert set(_ALL_PREFIXES) == registered


class TestCORSMiddleware:
    def test_cors_is_the_outermost_middleware(self, client):
        """Outermost, so an error from any other middleware still carries CORS headers."""
        from starlette.middleware.cors import CORSMiddleware

        assert client.app.user_middleware[0].cls is CORSMiddleware

    def test_cors_headers_on_options(self, client):
        resp = client.options(
            "/posts/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    def test_cors_allows_configured_origin(self, client):
        resp = client.options(
            "/posts/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestJWTExceptionHandler:
    def test_invalid_token_returns_422_with_a_fixed_message(self, client):
        resp = client.get(
            "/profile/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 422
        assert resp.json() == {"detail": "Invalid token"}

    def test_missing_token_on_protected_route(self, client):
        resp = client.get("/posts/following")
        assert resp.status_code == 401
        assert "detail" in resp.json()

    def test_valid_token_passes(self, client, create_user, auth_header):
        create_user("alice")
        resp = client.get("/profile/me", headers=auth_header("alice"))
        assert resp.status_code == 200

    def _stub_exc(self, status_code: int, message):
        """A real AuthJWTException (the handler only accepts that type)."""
        from app.common.auth_jwt import AuthJWTException

        return AuthJWTException(status_code, message)

    def _stub_request(self):
        from starlette.requests import Request

        return Request({"type": "http", "method": "GET", "path": "/x", "headers": []})

    @pytest.mark.parametrize(
        ("status_code", "message"),
        [
            (401, "Signature has expired"),
            (401, "Missing Authorization Header"),
            (422, "Invalid token"),
        ],
        ids=["expired", "missing", "invalid"],
    )
    def test_status_and_message_come_from_the_exception(self, status_code, message):
        """auth_jwt decides status and message; the handler only renders them.
        (It used to rewrite 422 to 401 by matching PyJWT's wording.)"""
        import json as _json

        from app.main import _authjwt_exception_handler

        response = _authjwt_exception_handler(
            self._stub_request(), self._stub_exc(status_code, message)
        )
        assert response.status_code == status_code
        assert _json.loads(bytes(response.body).decode()) == {"detail": message}

    def test_other_exception_types_are_not_swallowed(self):
        """The handler is registered for AuthJWTException only; anything else
        must propagate rather than be rendered as an auth error."""
        from app.main import _authjwt_exception_handler

        with pytest.raises(RuntimeError, match="boom"):
            _authjwt_exception_handler(self._stub_request(), RuntimeError("boom"))

    def test_empty_message_gets_default_detail(self):
        import json as _json

        from app.main import _authjwt_exception_handler

        response = _authjwt_exception_handler(
            self._stub_request(),
            self._stub_exc(401, None),
        )
        assert response.status_code == 401
        body = _json.loads(bytes(response.body).decode())
        assert body["detail"] == "Invalid or expired token"


class TestLifespan:
    """The lifespan context manager wraps `start_scheduler` and `stop_scheduler`."""

    def test_start_and_stop_called_around_yield(self):
        import asyncio

        from app.main import _lifespan

        with patch("app.main.start_scheduler") as start, patch("app.main.stop_scheduler") as stop:

            async def _run():
                async with _lifespan(MagicMock()):
                    start.assert_called_once()
                    stop.assert_not_called()
                stop.assert_called_once()

            asyncio.run(_run())

    def test_stop_called_even_on_exception(self):
        import asyncio

        from app.main import _lifespan

        with patch("app.main.start_scheduler") as start, patch("app.main.stop_scheduler") as stop:

            async def _run():
                with pytest.raises(RuntimeError):
                    async with _lifespan(MagicMock()):
                        raise RuntimeError("boom")
                stop.assert_called_once()
                start.assert_called_once()

            asyncio.run(_run())


class TestRoutersManifest:
    def test_manifest_prefixes_start_with_slash(self):
        from app.main import _ROUTERS

        for _, prefix in _ROUTERS:
            assert prefix.startswith("/"), f"{prefix!r} must start with '/'"

    def test_manifest_prefixes_unique(self):
        from app.main import _ROUTERS

        prefixes = [prefix for _, prefix in _ROUTERS]
        assert len(prefixes) == len(set(prefixes)), "duplicate prefix in _ROUTERS"
