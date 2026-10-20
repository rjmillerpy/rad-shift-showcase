"""API-level tests for app/metrics/views.py, through the real app."""

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.common.db import get_db
from app.main import create_app
from app.metrics.service import (
    METRICS_CONTENT_TYPE,
    METRICS_ENABLED_ENV_VAR,
    METRICS_PATH,
    metrics_enabled,
)

from .conftest import sample_value


def _scrape(client) -> str:
    return client.get(METRICS_PATH).text


class TestScrape:
    def test_ok_in_prometheus_text_format(self, client):
        resp = client.get(METRICS_PATH)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == METRICS_CONTENT_TYPE
        names = {family.name for family in text_string_to_metric_families(resp.text)}
        assert {"http_requests", "http_request_duration_seconds"} <= names

    def test_no_auth_required(self, client):
        """Like /health: kept off the internet by the proxy, not by a token."""
        assert client.get(METRICS_PATH).status_code == 200

    def test_includes_process_metrics(self, client):
        assert "process_resident_memory_bytes" in _scrape(client)


class TestRecordsRealTraffic:
    def test_counts_a_request_under_its_route_template(self, client):
        labels = {"method": "GET", "route": "/health/live", "status": "200"}
        before = sample_value(_scrape(client), "http_requests_total", **labels)

        client.get("/health/live")

        assert sample_value(_scrape(client), "http_requests_total", **labels) == before + 1

    def test_counts_a_503(self, client, unreachable_health_db):
        """The alert's input: a readiness failure is a 5xx."""
        labels = {"method": "GET", "route": "/health", "status": "503"}
        before = sample_value(_scrape(client), "http_requests_total", **labels)

        assert client.get("/health").status_code == 503

        assert sample_value(_scrape(client), "http_requests_total", **labels) == before + 1


class TestNotPartOfThePublicApi:
    def test_left_out_of_the_openapi_docs(self, client):
        assert METRICS_PATH not in client.app.openapi()["paths"]


class TestSwitchedOff:
    """METRICS_ENABLED=false, as ECS sets it (infra/ecs.tf)."""

    @pytest.fixture()
    def client_without_metrics(self, monkeypatch, db_session):
        monkeypatch.setenv(METRICS_ENABLED_ENV_VAR, "false")
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db_session
        with TestClient(app) as client:
            yield client

    def test_route_does_not_exist(self, client_without_metrics):
        assert client_without_metrics.get(METRICS_PATH).status_code == 404

    def test_rest_of_the_api_still_works(self, client_without_metrics):
        assert client_without_metrics.get("/health/live").status_code == 200

    @pytest.mark.parametrize(
        ("value", "enabled"),
        [("false", False), ("FALSE", False), ("true", True), ("", True)],
        ids=["false", "false-uppercase", "true", "empty"],
    )
    def test_only_false_turns_it_off(self, monkeypatch, value, enabled):
        monkeypatch.setenv(METRICS_ENABLED_ENV_VAR, value)
        assert metrics_enabled() is enabled

    def test_on_when_unset(self, monkeypatch):
        monkeypatch.delenv(METRICS_ENABLED_ENV_VAR, raising=False)
        assert metrics_enabled() is True
