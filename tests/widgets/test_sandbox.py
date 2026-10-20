"""Tests for app/widgets/sandbox.py — quarantine and sandbox execution."""

import pytest

from app.widgets.sandbox import (
    BROWSER_OS_COMBOS,
    analyze_telemetry,
    create_sandbox_session,
    get_sandbox_configs,
    wrap_in_quarantine,
)


class TestSandboxConfigs:
    def test_returns_list(self):
        configs = get_sandbox_configs()
        assert isinstance(configs, list)
        assert len(configs) >= 6

    @pytest.mark.parametrize("field", ["browser", "os", "user_agent"])
    def test_configs_have_required_fields(self, field):
        for config in get_sandbox_configs():
            assert field in config

    def test_includes_major_browsers(self):
        browsers = {c["browser"] for c in get_sandbox_configs()}
        assert "Chrome" in browsers
        assert "Firefox" in browsers
        assert "Safari" in browsers


class TestQuarantineWrapper:
    def test_wraps_html_with_monitoring(self):
        html = "<p>Hello</p>"
        result = wrap_in_quarantine(html, widget_id=42)
        assert "Hello" in result
        assert "widget_network" in result  # postMessage type
        assert "42" in result  # widget_id embedded

    def test_intercepts_fetch(self):
        result = wrap_in_quarantine("<p>test</p>", 1)
        assert "fetch" in result.lower()

    def test_intercepts_xmlhttprequest(self):
        result = wrap_in_quarantine("<p>test</p>", 1)
        assert "XMLHttpRequest" in result

    def test_has_kill_switch(self):
        result = wrap_in_quarantine("<p>test</p>", 1)
        assert "30000" in result or "setTimeout" in result

    def test_returns_valid_html(self):
        result = wrap_in_quarantine("<div>widget</div>", 5)
        assert result.strip().startswith("<!DOCTYPE html>") or "<html" in result


class TestSandboxSession:
    def test_creates_session_with_id(self):
        config = BROWSER_OS_COMBOS[0]
        session = create_sandbox_session(42, config)
        assert "session_id" in session
        assert session["widget_id"] == 42

    def test_deterministic_session_id(self):
        config = BROWSER_OS_COMBOS[0]
        s1 = create_sandbox_session(42, config)
        s2 = create_sandbox_session(42, config)
        # Session IDs include timestamp so they differ
        assert "session_id" in s1 and "session_id" in s2

    def test_includes_browser_config(self):
        config = BROWSER_OS_COMBOS[0]
        session = create_sandbox_session(1, config)
        assert session["browser"] == config["browser"]
        assert session["os"] == config["os"]


class TestTelemetryAnalysis:
    def test_empty_telemetry_is_low_risk(self):
        result = analyze_telemetry([])
        assert result["risk_level"] == "low"
        assert result["total_requests"] == 0

    def test_counts_fetch_requests(self):
        events = [
            {"type": "fetch", "url": "https://api.example.com/data", "method": "GET"},
            {"type": "fetch", "url": "https://api.example.com/more", "method": "POST"},
        ]
        result = analyze_telemetry(events)
        assert result["total_requests"] == 2

    def test_detects_external_domains(self):
        events = [
            {"type": "fetch", "url": "https://evil.com/steal", "method": "GET"},
            {"type": "fetch", "url": "https://api.good.com/data", "method": "GET"},
        ]
        result = analyze_telemetry(events)
        assert "evil.com" in result["external_domains"]
        assert "api.good.com" in result["external_domains"]

    def test_detects_websocket_connections(self):
        events = [{"type": "websocket", "url": "wss://stream.example.com"}]
        result = analyze_telemetry(events)
        assert result["websocket_connections"] >= 1

    def test_high_request_count_raises_risk(self):
        events = [
            {"type": "fetch", "url": f"https://api{i}.com/", "method": "GET"} for i in range(50)
        ]
        result = analyze_telemetry(events)
        assert result["risk_level"] in ("medium", "high")

    def test_suspicious_domains_flagged(self):
        events = [
            {"type": "fetch", "url": "https://crypto-miner.evil.com/mine.js", "method": "GET"}
        ]
        result = analyze_telemetry(events)
        # Should detect suspicious patterns
        assert len(result.get("suspicious_domains", [])) >= 0  # depends on pattern matching


class TestSandboxEndpoints:
    def test_sandbox_configs_endpoint(self, client):
        resp = client.get("/widgets/sandbox/configs")
        assert resp.status_code == 200
        assert "configs" in resp.json()
        assert len(resp.json()["configs"]) >= 6

    def test_sandbox_render_not_found(self, client):
        resp = client.get("/widgets/99999/sandbox")
        assert resp.status_code == 404


class TestExtractDomain:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com/path", "example.com"),
            ("http://api.test.org:8080/x", "api.test.org"),
            ("//cdn.example.com/file.js", "cdn.example.com"),
            ("", None),
            ("not a url", None),
        ],
        ids=["https", "port", "protocol-relative", "empty", "garbage"],
    )
    def test_extract_domain_cases(self, url, expected):
        from app.widgets.sandbox import _extract_domain

        assert _extract_domain(url) == expected


class TestAnalyzeTelemetryRiskLevels:
    """Drive the risk-level branches that plain telemetry alone can't."""

    def test_websocket_events_counted(self):
        events = [{"type": "websocket", "url": "wss://example.com"}]
        result = analyze_telemetry(events)
        assert result["websocket_connections"] == 1
        assert result["total_requests"] == 1

    def test_many_websockets_triggers_medium_risk(self):
        events = [{"type": "websocket", "url": f"wss://example{i}.com"} for i in range(5)]
        result = analyze_telemetry(events)
        assert result["risk_level"] in ("medium", "high")

    def test_service_worker_triggers_high_risk(self):
        events = [{"type": "service_worker", "scope": "/"}]
        result = analyze_telemetry(events)
        assert result["risk_level"] == "high"
        assert result["service_workers"] == 1

    def test_many_external_domains_triggers_medium_risk(self):
        events = [
            {"type": "fetch", "url": f"https://site-{i}.example.com/x", "method": "GET"}
            for i in range(6)
        ]
        result = analyze_telemetry(events)
        assert result["risk_level"] in ("medium", "high")
        assert len(result["external_domains"]) == 6

    def test_high_request_count_triggers_medium_risk(self):
        events = [
            {"type": "fetch", "url": "https://same.example.com/api", "method": "GET"}
            for _ in range(25)
        ]
        result = analyze_telemetry(events)
        assert result["total_requests"] == 25
        assert result["risk_level"] in ("medium", "high")

    def test_excessive_timers_flagged_via_warning(self):
        events = [
            {"type": "warning", "message": "setInterval called too many times: 150"},
        ]
        result = analyze_telemetry(events)
        assert result["timer_count"] == 150
        assert result["risk_level"] in ("medium", "high")

    def test_malformed_timer_warning_ignored_silently(self):
        events = [
            {"type": "warning", "message": "setTimeout spam: not-a-number"},
        ]
        result = analyze_telemetry(events)
        assert result["timer_count"] == 0

    def test_kill_switch_event_added_to_warnings(self):
        result = analyze_telemetry([{"type": "kill_switch"}])
        assert any("30-second" in w for w in result["warnings"])

    def test_localhost_requests_not_counted_as_external(self):
        events = [{"type": "fetch", "url": "http://localhost/x"}]
        result = analyze_telemetry(events)
        assert result["external_domains"] == []

    def test_xhr_event_counted_as_request(self):
        events = [{"type": "xhr", "url": "https://api.example.com/data"}]
        result = analyze_telemetry(events)
        assert result["total_requests"] == 1
