"""Post-run telemetry analysis for widget sandbox sessions.

Split out from ``sandbox.py`` (which was 389 lines — one addition from breaking
the 400-line cap) so the quarantine wrapper and the analysis pass live in
separate modules with their own reasons to change (rule 55).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Domains known to host malicious payloads, miners, or trackers.
SUSPICIOUS_DOMAIN_PATTERNS: list[str] = [
    "coinhive.com",
    "cryptoloot.pro",
    "coin-hive.com",
    "jsecoin.com",
    "authedmine.com",
    "ppoi.org",
    "minero.cc",
    "webmine.cz",
    "keylogger",
    "evil",
    "malware",
    "phishing",
]

# Local addresses that shouldn't count as "external" for network-fanout risk.
_LOCAL_HOSTS = {"localhost", "127.0.0.1"}

# Risk thresholds — extracted so tests can pin the exact triage bar.
WEBSOCKET_MEDIUM_THRESHOLD = 3
DOMAIN_FANOUT_MEDIUM_THRESHOLD = 5
REQUESTS_MEDIUM_THRESHOLD = 20
TIMER_MEDIUM_THRESHOLD = 100

KILL_SWITCH_WARNING = "Widget hit the 30-second execution limit"


def _extract_domain(url: str) -> str | None:
    """Extract the domain from a URL, returning None if the URL is unparseable."""
    try:
        return urlparse(url).hostname
    except (ValueError, AttributeError):
        # `urlparse` mostly tolerates junk, but a caller can hand us a non-str
        # or a totally malformed URL. Silence is deliberate: a bad URL just
        # means "we can't attribute this request to a domain" — not an error.
        return None


def _is_suspicious_domain(domain: str) -> bool:
    domain_lower = domain.lower()
    return any(pattern in domain_lower for pattern in SUSPICIOUS_DOMAIN_PATTERNS)


def _classify_domain(url: str, external: set[str], suspicious: set[str]) -> None:
    """Record `url`'s domain in the external/suspicious buckets if applicable."""
    domain = _extract_domain(url)
    if not domain or domain in _LOCAL_HOSTS:
        return
    external.add(domain)
    if _is_suspicious_domain(domain):
        suspicious.add(domain)


def _timer_count_from_warning(msg: str) -> int | None:
    """Parse the trailing count from a warning like 'Excessive setInterval calls: 42'."""
    if "setInterval" not in msg and "setTimeout" not in msg:
        return None
    try:
        return int(msg.split(":")[-1].strip())
    except (ValueError, IndexError):
        return None


def _assess_risk(
    suspicious: set[str],
    service_workers: int,
    websockets: int,
    external_domains: set[str],
    total_requests: int,
    timer_count: int,
) -> tuple[str, list[str]]:
    """Given the accumulated counters, return (risk_level, reasons)."""
    reasons: list[str] = []
    high = False
    medium = False

    if suspicious:
        high = True
        reasons.append(f"Suspicious domains contacted: {', '.join(sorted(suspicious))}")
    if service_workers > 0:
        high = True
        reasons.append(f"Service worker registration attempted ({service_workers})")
    if websockets > WEBSOCKET_MEDIUM_THRESHOLD:
        medium = True
        reasons.append(f"Many WebSocket connections ({websockets})")
    if len(external_domains) > DOMAIN_FANOUT_MEDIUM_THRESHOLD:
        medium = True
        reasons.append(f"Many external domains contacted ({len(external_domains)})")
    if total_requests > REQUESTS_MEDIUM_THRESHOLD:
        medium = True
        reasons.append(f"High number of network requests ({total_requests})")
    if timer_count > TIMER_MEDIUM_THRESHOLD:
        medium = True
        reasons.append(f"Excessive timer usage ({timer_count})")

    if high:
        return "high", reasons
    if medium:
        return "medium", reasons
    return "low", reasons


@dataclass
class _Tally:
    """Running totals while walking a session's events."""

    total_requests: int = 0
    external_domains: set[str] = field(default_factory=set)
    suspicious_domains: set[str] = field(default_factory=set)
    websocket_connections: int = 0
    service_workers: int = 0
    timer_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _record_request(tally: _Tally, event: dict) -> None:
    tally.total_requests += 1
    _classify_domain(event.get("url", ""), tally.external_domains, tally.suspicious_domains)


def _record_websocket(tally: _Tally, event: dict) -> None:
    tally.websocket_connections += 1
    _record_request(tally, event)


def _record_service_worker(tally: _Tally, _event: dict) -> None:
    tally.service_workers += 1


def _record_warning(tally: _Tally, event: dict) -> None:
    message = event.get("message", "")
    tally.warnings.append(message)
    reported_timers = _timer_count_from_warning(message)
    if reported_timers is not None:
        tally.timer_count = max(tally.timer_count, reported_timers)


def _record_kill_switch(tally: _Tally, _event: dict) -> None:
    tally.warnings.append(KILL_SWITCH_WARNING)


# Event type -> what it adds to the tally. Unknown types are ignored.
_EVENT_HANDLERS: dict[str, Callable[[_Tally, dict], None]] = {
    "fetch": _record_request,
    "xhr": _record_request,
    "eventsource": _record_request,
    "websocket": _record_websocket,
    "service_worker": _record_service_worker,
    "warning": _record_warning,
    "kill_switch": _record_kill_switch,
}


def _tally_events(telemetry: list[dict]) -> _Tally:
    tally = _Tally()
    for event in telemetry:
        handler = _EVENT_HANDLERS.get(event.get("type", ""))
        if handler is not None:
            handler(tally, event)
    return tally


def analyze_telemetry(telemetry: list[dict]) -> dict:
    """Analyze captured network telemetry from a sandbox session.

    Returns an analysis dict with request counts, domain lists, and a triaged
    risk level (low/medium/high) with human-readable reasons.
    """
    tally = _tally_events(telemetry)
    risk_level, risk_reasons = _assess_risk(
        tally.suspicious_domains,
        tally.service_workers,
        tally.websocket_connections,
        tally.external_domains,
        tally.total_requests,
        tally.timer_count,
    )

    logger.info(
        "Telemetry analysis: requests=%d, domains=%d, suspicious=%d, risk=%s",
        tally.total_requests,
        len(tally.external_domains),
        len(tally.suspicious_domains),
        risk_level,
    )

    return {
        "total_requests": tally.total_requests,
        "external_domains": sorted(tally.external_domains),
        "suspicious_domains": sorted(tally.suspicious_domains),
        "websocket_connections": tally.websocket_connections,
        "service_workers": tally.service_workers,
        "timer_count": tally.timer_count,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "warnings": tally.warnings,
    }
