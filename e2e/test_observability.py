"""Metrics, logs, dashboard and alert email (compose.observability.yaml, roadmap item 15).

Runs only with the overlay (`E2E_OBS=1 e2e/run.sh`). Each test follows one
signal from the app to where a person would see it. The last one is a real
outage drill: it stops the API and waits for the email.
"""

import time
from collections.abc import Callable

import httpx
import pytest

from e2e.helpers import OBSERVABILITY, compose

pytestmark = pytest.mark.skipif(
    not OBSERVABILITY, reason="observability overlay only: E2E_OBS=1 e2e/run.sh"
)

PROMETHEUS = "http://localhost:9090"
ALERTMANAGER = "http://localhost:9093"
GRAFANA = "http://localhost:3001"
MAILPIT = "http://localhost:8025"
GRAFANA_ADMIN = ("admin", "radshift-local")  # compose.observability.yaml default
REQUEST_TIMEOUT_SECONDS = 10
POLL_INTERVAL_SECONDS = 2
# One 15 s scrape interval plus slack for the first scrape after start.
SCRAPE_WAIT_SECONDS = 60
# Alloy discovers containers, tails them and pushes in batches.
LOG_WAIT_SECONDS = 60
# Scrape (15 s) + `for: 1m` + evaluation (15 s) + Alertmanager group_wait (30 s) + slack.
DRILL_WAIT_SECONDS = 240


def _wait_for[T](probe: Callable[[], T | None], timeout: float, what: str) -> T:
    """Call probe until it returns something truthy; fail after timeout seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"{what}: not seen within {timeout:.0f} s")


def _prometheus_query(expr: str) -> list[dict]:
    response = httpx.get(
        f"{PROMETHEUS}/api/v1/query", params={"query": expr}, timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()["data"]["result"]


def _alert_emails(alertname: str) -> list[dict]:
    response = httpx.get(
        f"{MAILPIT}/api/v1/search", params={"query": alertname}, timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()["messages"]


def test_prometheus_scrapes_the_api() -> None:
    result = _wait_for(
        lambda: _prometheus_query('up{job="backend"} == 1'), SCRAPE_WAIT_SECONDS, "backend up"
    )
    assert result[0]["metric"]["instance"] == "backend:5000"


def test_requests_are_counted_by_route_template(api: httpx.Client) -> None:
    for post_id in (1, 2, 3):
        api.get(f"/posts/{post_id}/replies")
    expr = 'http_requests_total{job="backend", route="/posts/{post_id}/replies"}'
    result = _wait_for(lambda: _prometheus_query(expr), SCRAPE_WAIT_SECONDS, "reply requests")
    # One series per status, never one per post id.
    assert {series["metric"]["route"] for series in result} == {"/posts/{post_id}/replies"}


def test_alert_rules_are_loaded() -> None:
    response = httpx.get(f"{PROMETHEUS}/api/v1/rules", timeout=REQUEST_TIMEOUT_SECONDS)
    rules = [rule for group in response.json()["data"]["groups"] for rule in group["rules"]]
    assert {rule["name"] for rule in rules} == {"HighServerErrorRate", "BackendDown"}
    assert all(rule["health"] == "ok" for rule in rules)


def test_api_logs_reach_loki_through_grafana(api: httpx.Client) -> None:
    api.get("/health")

    def backend_log_lines() -> list[dict]:
        # Through Grafana's datasource proxy: proves the provisioned Loki
        # datasource works, not just that Loki has data.
        response = httpx.get(
            f"{GRAFANA}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
            params={"query": '{service="backend"}', "limit": "10", "since": "10m"},
            auth=GRAFANA_ADMIN,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["data"]["result"]

    streams = _wait_for(backend_log_lines, LOG_WAIT_SECONDS, "backend logs in Loki")
    assert streams[0]["stream"]["project"].startswith("radshift")


def test_dashboard_is_provisioned_for_anonymous_viewers() -> None:
    response = httpx.get(f"{GRAFANA}/api/dashboards/uid/rad-shift", timeout=REQUEST_TIMEOUT_SECONDS)
    assert response.status_code == 200
    assert response.json()["meta"]["provisioned"] is True


@pytest.mark.parametrize("uid", ["prometheus", "loki"])
def test_grafana_datasources_are_healthy(uid: str) -> None:
    response = httpx.get(
        f"{GRAFANA}/api/datasources/uid/{uid}/health",
        auth=GRAFANA_ADMIN,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    assert response.json()["status"] == "OK"


def test_drill_stopping_the_api_emails_backend_down() -> None:
    """The whole alert path, for real: Prometheus sees failed scrapes,
    BackendDown fires after a minute, Alertmanager emails, Mailpit catches it.
    The API is started again afterwards for the tests that follow."""
    assert not _alert_emails("BackendDown"), "stale alert email from an earlier run"
    started = time.monotonic()
    compose("stop", "backend")
    try:
        emails = _wait_for(
            lambda: _alert_emails("BackendDown"), DRILL_WAIT_SECONDS, "BackendDown email"
        )
        print(f"BackendDown email {time.monotonic() - started:.0f} s after the API stopped")
        assert "[FIRING:1] BackendDown" in emails[0]["Subject"]
    finally:
        compose("up", "-d", "--wait", "backend")
