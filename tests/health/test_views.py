"""API-level tests for app/health/views.py."""

import pytest

from app.common.db import get_db


@pytest.fixture()
def client_without_database(client, unreachable_db):
    """The app, with its database dependency pointed at one that is down."""
    client.app.dependency_overrides[get_db] = lambda: unreachable_db
    return client


class TestLive:
    def test_ok(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_stays_ok_during_a_database_outage(self, client_without_database):
        """Liveness must not depend on the database (see service.liveness)."""
        assert client_without_database.get("/health/live").status_code == 200


class TestReady:
    def test_ok_when_database_answers(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "checks": {"database": "ok"}}

    def test_503_when_database_is_down(self, client_without_database):
        resp = client_without_database.get("/health")
        assert resp.status_code == 503
        assert resp.json() == {"status": "unavailable", "checks": {"database": "unavailable"}}

    def test_failure_detail_is_not_returned(self, client_without_database):
        """Unauthenticated endpoint: no driver message, path or SQL in the body."""
        body = client_without_database.get("/health").text
        assert "unable to open" not in body
        assert "sqlite" not in body.lower()
        assert "SELECT" not in body


class TestContract:
    """Shared by both endpoints: no credentials needed, never cached."""

    @pytest.mark.parametrize("path", ["/health", "/health/live"], ids=["ready", "live"])
    def test_no_auth_required(self, client, path):
        assert client.get(path).status_code == 200

    @pytest.mark.parametrize("path", ["/health", "/health/live"], ids=["ready", "live"])
    def test_never_cached(self, client, path):
        assert client.get(path).headers["cache-control"] == "no-store"

    def test_503_is_never_cached_either(self, client_without_database):
        assert client_without_database.get("/health").headers["cache-control"] == "no-store"

    @pytest.mark.parametrize("path", ["/health", "/health/live"], ids=["ready", "live"])
    def test_documented_with_a_response_schema(self, client, path):
        """Rule 46: the OpenAPI schema names a model, not a free-form object."""
        schema = client.app.openapi()["paths"][path]["get"]["responses"]["200"]
        assert "$ref" in schema["content"]["application/json"]["schema"]
