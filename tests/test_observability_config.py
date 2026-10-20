"""The observability configs (roadmap item 15) agree with the app and with each other.

The tools check their own syntax (observability/check.sh). What they can't
see is drift between files: a dashboard querying a metric the app stopped
exporting shows "No data" instead of failing, and an alert threshold changed
in one place but not the other means local and AWS disagree on an outage.
"""

import json
import re
from ipaddress import ip_address, ip_network
from pathlib import Path

import pytest
import yaml
from prometheus_client.parser import text_string_to_metric_families

from app.metrics.service import METRICS_PATH

ROOT = Path(__file__).resolve().parent.parent
OBSERVABILITY = ROOT / "observability"
DASHBOARD = OBSERVABILITY / "grafana" / "dashboards" / "rad-shift.json"
DATASOURCES = OBSERVABILITY / "grafana" / "provisioning" / "datasources" / "datasources.yml"
ALERTS = OBSERVABILITY / "prometheus" / "alerts.yml"
COMPOSE = ROOT / "compose.observability.yaml"

# Series Prometheus adds itself for every scrape target.
SCRAPE_SERIES = {"up"}

# A metric name directly followed by a label matcher or a range: "name{" or "name[".
_METRIC_IN_PROMQL = re.compile(r"\b([a-z_][a-z0-9_]*)\s*[{\[]")
_EXACT_IMAGE_TAG = re.compile(r"^[\w./-]+:v?\d+\.\d+\.\d+$")


def _dashboard() -> dict:
    return json.loads(DASHBOARD.read_text())


def _alert_rules() -> list[dict]:
    return [
        rule for group in yaml.safe_load(ALERTS.read_text())["groups"] for rule in group["rules"]
    ]


def _promql_queries() -> list[str]:
    dashboard = [
        target["expr"]
        for panel in _dashboard()["panels"]
        if panel["datasource"]["type"] == "prometheus"
        for target in panel["targets"]
    ]
    return dashboard + [rule["expr"] for rule in _alert_rules()]


def _exported_series(client) -> set[str]:
    client.get("/health/live")  # so the labelled metrics have samples
    body = client.get(METRICS_PATH).text
    return {
        sample.name for family in text_string_to_metric_families(body) for sample in family.samples
    }


class TestQueriesUseRealMetrics:
    def test_every_metric_queried_is_exported(self, client):
        queried = {name for query in _promql_queries() for name in _METRIC_IN_PROMQL.findall(query)}
        unknown = queried - _exported_series(client) - SCRAPE_SERIES
        assert not unknown, f"queried but not exported by the app: {sorted(unknown)}"

    def test_the_scanner_finds_metrics(self):
        """Guards the guard: an empty scan would make the test above pass vacuously."""
        queried = {name for query in _promql_queries() for name in _METRIC_IN_PROMQL.findall(query)}
        assert {"http_requests_total", "http_request_duration_seconds_bucket", "up"} <= queried


class TestDashboard:
    def test_every_datasource_is_provisioned(self):
        provisioned = {
            source["uid"] for source in yaml.safe_load(DATASOURCES.read_text())["datasources"]
        }
        used = {panel["datasource"]["uid"] for panel in _dashboard()["panels"]}
        assert used <= provisioned

    def test_panel_ids_are_unique(self):
        ids = [panel["id"] for panel in _dashboard()["panels"]]
        assert len(ids) == len(set(ids))

    def test_read_only(self):
        """Provisioned from the repo; UI edits would be lost on restart."""
        assert _dashboard()["editable"] is False


class TestOneThresholdForLocalAndAws:
    def test_prometheus_rule_and_cloudwatch_alarm_agree(self):
        rule = next(r for r in _alert_rules() if r["alert"] == "HighServerErrorRate")
        local_ratio = float(re.search(r"\)\s*>\s*([\d.]+)", rule["expr"]).group(1))
        variables = (ROOT / "infra" / "variables.tf").read_text()
        block = re.search(r'variable "error_rate_threshold_percent" \{(.*?)\n\}', variables, re.S)
        aws_percent = float(re.search(r"default\s*=\s*([\d.]+)", block.group(1)).group(1))
        assert local_ratio * 100 == aws_percent

    def test_both_wait_five_minutes(self):
        rule = next(r for r in _alert_rules() if r["alert"] == "HighServerErrorRate")
        monitoring = (ROOT / "infra" / "monitoring.tf").read_text()
        assert rule["for"] == "5m"
        assert re.search(r"alarm_period_seconds\s*=\s*60\b", monitoring)
        assert re.search(r"alarm_evaluation_periods\s*=\s*5\b", monitoring)


class TestStack:
    @pytest.mark.parametrize(
        "service", list(yaml.safe_load(COMPOSE.read_text())["services"]), ids=str
    )
    def test_images_pinned_to_an_exact_version(self, service):
        image = yaml.safe_load(COMPOSE.read_text())["services"][service]["image"]
        assert _EXACT_IMAGE_TAG.match(image), f"{service}: {image} is not an exact version"

    @pytest.mark.parametrize(
        "service", list(yaml.safe_load(COMPOSE.read_text())["services"]), ids=str
    )
    def test_ui_ports_listen_on_loopback_only(self, service):
        for mapping in yaml.safe_load(COMPOSE.read_text())["services"][service].get("ports", []):
            assert mapping.startswith("127.0.0.1:"), (
                f"{service} publishes {mapping} beyond localhost"
            )

    def test_proxy_hides_the_metrics_endpoint(self):
        caddyfile = (ROOT / "caddy" / "Caddyfile").read_text()
        assert f"@metrics path {METRICS_PATH} {METRICS_PATH}/*" in caddyfile
        assert "respond @metrics 404" in caddyfile


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that also reads Compose's merge tags (`ports: !reset []`)."""


_ComposeLoader.add_constructor("!reset", lambda loader, node: None)
_ComposeLoader.add_constructor("!override", lambda loader, node: None)


class TestTlsOverlayWithMoreContainers:
    """compose.tls.yaml gives Caddy a fixed address; the observability overlay
    adds six containers that take dynamic ones from the same network."""

    def test_fixed_proxy_address_is_outside_the_dynamic_range(self):
        tls = yaml.load(
            (ROOT / "compose.tls.yaml").read_text(), Loader=_ComposeLoader
        )  # a SafeLoader subclass: still safe
        network = tls["networks"]["default"]["ipam"]["config"][0]
        caddy_ip = ip_address(tls["services"]["caddy"]["networks"]["default"]["ipv4_address"])
        assert caddy_ip in ip_network(network["subnet"])
        assert caddy_ip not in ip_network(network["ip_range"])
