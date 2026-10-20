"""Direct unit tests for app/widgets/_sandbox_telemetry.py.

The public API is also re-exported by ``sandbox.py`` and covered indirectly by
tests/widgets/test_sandbox.py; these tests pin the extracted internals so a
future refactor can safely move code between the two.
"""

import pytest

from app.widgets._sandbox_telemetry import (
    DOMAIN_FANOUT_MEDIUM_THRESHOLD,
    REQUESTS_MEDIUM_THRESHOLD,
    TIMER_MEDIUM_THRESHOLD,
    WEBSOCKET_MEDIUM_THRESHOLD,
    _classify_domain,
    _extract_domain,
    _is_suspicious_domain,
    _timer_count_from_warning,
    analyze_telemetry,
)


class TestExtractDomain:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com/path", "example.com"),
            ("http://sub.example.com:8080/x", "sub.example.com"),
            ("//example.com/x", "example.com"),
            ("", None),
            ("not a url at all", None),
        ],
        ids=["https", "port", "protocol_relative", "empty", "garbage"],
    )
    def test_extract(self, url, expected):
        assert _extract_domain(url) == expected


class TestIsSuspiciousDomain:
    @pytest.mark.parametrize(
        "domain",
        ["evil.example.com", "coinhive.com", "totally-malware.io"],
        ids=["evil", "cryptominer", "malware"],
    )
    def test_flags_suspicious(self, domain):
        assert _is_suspicious_domain(domain) is True

    def test_clean_domain(self):
        assert _is_suspicious_domain("example.com") is False


class TestClassifyDomain:
    def test_local_hosts_ignored(self):
        external: set[str] = set()
        suspicious: set[str] = set()
        _classify_domain("http://localhost/x", external, suspicious)
        _classify_domain("http://127.0.0.1/x", external, suspicious)
        assert external == set()

    def test_external_added(self):
        external: set[str] = set()
        suspicious: set[str] = set()
        _classify_domain("https://example.com/x", external, suspicious)
        assert external == {"example.com"}
        assert suspicious == set()

    def test_suspicious_added_to_both(self):
        external: set[str] = set()
        suspicious: set[str] = set()
        _classify_domain("https://coinhive.com/x", external, suspicious)
        assert "coinhive.com" in external
        assert "coinhive.com" in suspicious


class TestTimerCountFromWarning:
    def test_setinterval(self):
        assert _timer_count_from_warning("Excessive setInterval calls: 42") == 42

    def test_settimeout(self):
        assert _timer_count_from_warning("Excessive setTimeout calls: 900") == 900

    def test_unrelated_returns_none(self):
        assert _timer_count_from_warning("something else entirely") is None

    def test_malformed_returns_none(self):
        assert _timer_count_from_warning("setInterval calls: nope") is None


class TestAnalyzeTelemetry:
    def test_empty_is_low_risk(self):
        result = analyze_telemetry([])
        assert result["risk_level"] == "low"
        assert result["total_requests"] == 0

    def test_suspicious_domain_is_high_risk(self):
        result = analyze_telemetry(
            [
                {"type": "fetch", "url": "https://coinhive.com/miner.js"},
            ]
        )
        assert result["risk_level"] == "high"

    def test_service_worker_is_high_risk(self):
        result = analyze_telemetry([{"type": "service_worker", "url": "/sw.js"}])
        assert result["risk_level"] == "high"

    def test_many_websockets_is_medium(self):
        events = [
            {"type": "websocket", "url": f"wss://example{i}.com/"}
            for i in range(WEBSOCKET_MEDIUM_THRESHOLD + 1)
        ]
        assert analyze_telemetry(events)["risk_level"] == "medium"

    def test_many_domains_is_medium(self):
        events = [
            {"type": "fetch", "url": f"https://example{i}.com/x"}
            for i in range(DOMAIN_FANOUT_MEDIUM_THRESHOLD + 1)
        ]
        assert analyze_telemetry(events)["risk_level"] == "medium"

    def test_many_requests_is_medium(self):
        events = [
            {"type": "fetch", "url": "https://example.com/x"}
            for _ in range(REQUESTS_MEDIUM_THRESHOLD + 1)
        ]
        assert analyze_telemetry(events)["risk_level"] == "medium"

    def test_high_timer_count_is_medium(self):
        events = [
            {
                "type": "warning",
                "message": f"Excessive setInterval calls: {TIMER_MEDIUM_THRESHOLD + 1}",
            },
        ]
        assert analyze_telemetry(events)["risk_level"] == "medium"

    def test_kill_switch_is_recorded(self):
        result = analyze_telemetry([{"type": "kill_switch"}])
        assert any("30-second" in w for w in result["warnings"])

    def test_local_host_not_external(self):
        result = analyze_telemetry(
            [
                {"type": "fetch", "url": "http://localhost/health"},
            ]
        )
        assert result["external_domains"] == []
