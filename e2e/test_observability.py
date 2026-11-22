"""Metrics, logs, dashboard and alert email (compose.observability.yaml, roadmap items 15, 24 and 26).

Runs only with the overlay (`E2E_OBS=1 e2e/run.sh`). Each test follows one
signal from the app to where a person would see it. The last one is a real
outage drill: it stops the API and waits for the email.
"""

import json
import time
import uuid
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
# The backend batches spans (up to 5 s) before Tempo can return the trace.
TRACE_WAIT_SECONDS = 60
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


def _loki_streams(query: str) -> list[dict]:
    # Through Grafana's datasource proxy: proves the provisioned Loki
    # datasource works, not just that Loki has data.
    response = httpx.get(
        f"{GRAFANA}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
        params={"query": query, "limit": "10", "since": "10m"},
        auth=GRAFANA_ADMIN,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["data"]["result"]


def test_a_request_can_be_found_in_loki_by_its_id(api: httpx.Client) -> None:
    """Item 24: the id a user would see in a response header leads to the
    server's JSON line, with level as a label and the id as structured metadata."""
    request_id = f"e2e-{uuid.uuid4().hex}"
    response = api.get("/posts/", headers={"X-Request-ID": request_id})
    assert response.headers["X-Request-ID"] == request_id

    streams = _wait_for(
        lambda: _loki_streams(f'{{service="backend", level="info"}} | request_id="{request_id}"'),
        LOG_WAIT_SECONDS,
        "the request's log line in Loki",
    )
    (stream,) = streams
    assert stream["stream"]["project"].startswith("radshift")
    (_, line), *_ = stream["values"]
    fields = json.loads(line)
    assert (fields["event"], fields["route"], fields["status"]) == ("http.request", "/posts/", 200)


def _span_names(trace: object) -> list[str]:
    """Every span name in a Tempo trace response, whatever its nesting."""
    if isinstance(trace, dict):
        own = [trace["name"]] if "spanId" in trace and "name" in trace else []
        return own + [name for value in trace.values() for name in _span_names(value)]
    if isinstance(trace, list):
        return [name for value in trace for name in _span_names(value)]
    return []


def _tempo_spans(trace_id: str) -> list[str]:
    response = httpx.get(
        f"{GRAFANA}/api/datasources/proxy/uid/tempo/api/v2/traces/{trace_id}",
        auth=GRAFANA_ADMIN,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:  # not flushed or ingested yet
        return []
    response.raise_for_status()
    return _span_names(response.json())


def test_a_request_is_traced_and_its_logs_carry_the_trace_id(api: httpx.Client) -> None:
    """Item 26: a caller's W3C traceparent is continued through the API; the
    trace reaches Tempo with a SQL child span, and the request's log line in
    Loki carries the same trace id (what Grafana's "View trace" link uses)."""
    trace_id = uuid.uuid4().hex
    traceparent = f"00-{trace_id}-{uuid.uuid4().hex[:16]}-01"
    assert api.get("/posts/", headers={"traceparent": traceparent}).status_code == 200

    names = _wait_for(lambda: _tempo_spans(trace_id), TRACE_WAIT_SECONDS, "the trace in Tempo")
    assert "GET /posts/" in names
    assert any(name.startswith(("SELECT", "connect")) for name in names), names

    streams = _wait_for(
        lambda: _loki_streams(f'{{service="backend"}} | trace_id="{trace_id}"'),
        LOG_WAIT_SECONDS,
        "the request's log line with its trace id",
    )
    (_, line), *_ = streams[0]["values"]
    assert json.loads(line)["route"] == "/posts/"


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
