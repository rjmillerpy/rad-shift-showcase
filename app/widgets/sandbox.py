"""Widget sandbox and quarantine system.

Provides:
- Browser/OS configurations for cross-target testing.
- Quarantined execution environment that wraps widget HTML with monitoring code
  (network interception, service-worker blocking, timer/DOM tracking, kill-switch).
- Session metadata for a single sandbox run.

Post-run telemetry analysis lives in ``_sandbox_telemetry.py`` and is
re-exported from this module so external callers keep their existing imports.
"""

import hashlib
import json
import logging
import time

from ._sandbox_telemetry import (  # re-exported public API (backwards compat)
    SUSPICIOUS_DOMAIN_PATTERNS,
    _extract_domain,
    analyze_telemetry,
)

logger = logging.getLogger(__name__)


# Kill-switch timer for a single sandbox iframe run.
KILL_SWITCH_MS = 30_000
# Warning thresholds surfaced to the parent as telemetry events.
TIMER_WARN_INTERVAL_COUNT = 100
TIMER_WARN_TIMEOUT_COUNT = 500
INITIAL_TELEMETRY_DELAY_MS = 500
# SHA-256 prefix used as the sandbox session id.
SESSION_ID_HEX_LEN = 16


# Supported browser/OS combos for testing.
BROWSER_OS_COMBOS: list[dict[str, str]] = [
    {
        "browser": "Chrome",
        "os": "Windows 11",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    },
    {
        "browser": "Firefox",
        "os": "Windows 11",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    },
    {
        "browser": "Safari",
        "os": "macOS Sonoma",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 Safari/605.1.15",
    },
    {
        "browser": "Chrome",
        "os": "Android 14",
        "user_agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile",
    },
    {
        "browser": "Safari",
        "os": "iOS 17",
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    },
    {
        "browser": "Edge",
        "os": "Windows 11",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/120.0.0.0",
    },
    {
        "browser": "Chrome",
        "os": "Linux",
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    },
    {
        "browser": "Firefox",
        "os": "Linux",
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    },
]


def get_sandbox_configs() -> list[dict[str, str]]:
    """Return the list of available browser/OS configurations for sandbox testing."""
    return BROWSER_OS_COMBOS


# Injected ahead of the widget's own markup. A str.format template, so literal
# JavaScript braces are doubled.
_MONITORING_JS_TEMPLATE = """
<script>
(function() {{
  "use strict";
  var WIDGET_ID = {widget_id};
  var _log = [];
  var _timerCount = 0;
  var _mutationCount = 0;
  var _wsCount = 0;
  var _swCount = 0;

  function _sendTelemetry() {{
    try {{
      window.parent.postMessage({{
        type: "widget_network",
        widget_id: WIDGET_ID,
        log: _log,
        timers: _timerCount,
        mutations: _mutationCount,
        websockets: _wsCount,
        service_workers: _swCount
      }}, "*");
    }} catch(e) {{}}
  }}

  // -- Intercept fetch --
  var _originalFetch = window.fetch;
  window.fetch = function(url, opts) {{
    var entry = {{
      type: "fetch",
      url: String(url),
      method: (opts || {{}}).method || "GET",
      ts: Date.now()
    }};
    if (opts && opts.headers) {{
      try {{ entry.headers = JSON.parse(JSON.stringify(opts.headers)); }} catch(e) {{}}
    }}
    _log.push(entry);
    _sendTelemetry();
    return _originalFetch.apply(this, arguments);
  }};

  // -- Intercept XMLHttpRequest --
  var _OrigXHR = window.XMLHttpRequest;
  function MonitoredXHR() {{
    var xhr = new _OrigXHR();
    var _origOpen = xhr.open;
    var _origSetHeader = xhr.setRequestHeader;
    var _headers = {{}};
    xhr.open = function(method, url) {{
      xhr._monMethod = method;
      xhr._monUrl = String(url);
      return _origOpen.apply(xhr, arguments);
    }};
    xhr.setRequestHeader = function(name, value) {{
      _headers[name] = value;
      return _origSetHeader.apply(xhr, arguments);
    }};
    var _origSend = xhr.send;
    xhr.send = function() {{
      _log.push({{
        type: "xhr",
        url: xhr._monUrl || "",
        method: xhr._monMethod || "GET",
        headers: Object.keys(_headers).length > 0 ? _headers : undefined,
        ts: Date.now()
      }});
      _sendTelemetry();
      return _origSend.apply(xhr, arguments);
    }};
    return xhr;
  }}
  window.XMLHttpRequest = MonitoredXHR;

  // -- Intercept WebSocket --
  var _OrigWS = window.WebSocket;
  window.WebSocket = function(url, protocols) {{
    _wsCount++;
    _log.push({{
      type: "websocket",
      url: String(url),
      ts: Date.now()
    }});
    _sendTelemetry();
    return new _OrigWS(url, protocols);
  }};
  window.WebSocket.prototype = _OrigWS.prototype;

  // -- Intercept EventSource --
  if (window.EventSource) {{
    var _OrigES = window.EventSource;
    window.EventSource = function(url, opts) {{
      _log.push({{
        type: "eventsource",
        url: String(url),
        ts: Date.now()
      }});
      _sendTelemetry();
      return new _OrigES(url, opts);
    }};
    window.EventSource.prototype = _OrigES.prototype;
  }}

  // -- Intercept service worker registration --
  if (navigator.serviceWorker) {{
    var _origRegister = navigator.serviceWorker.register;
    navigator.serviceWorker.register = function(url) {{
      _swCount++;
      _log.push({{
        type: "service_worker",
        url: String(url),
        ts: Date.now()
      }});
      _sendTelemetry();
      return Promise.reject(new Error("Service worker registration blocked in sandbox"));
    }};
  }}

  // -- Monitor timers --
  var _origSetInterval = window.setInterval;
  window.setInterval = function() {{
    _timerCount++;
    if (_timerCount > {TIMER_WARN_INTERVAL_COUNT}) {{
      _log.push({{type: "warning", message: "Excessive setInterval calls: " + _timerCount, ts: Date.now()}});
      _sendTelemetry();
    }}
    return _origSetInterval.apply(window, arguments);
  }};

  var _origSetTimeout = window.setTimeout;
  window.setTimeout = function() {{
    _timerCount++;
    if (_timerCount > {TIMER_WARN_TIMEOUT_COUNT}) {{
      _log.push({{type: "warning", message: "Excessive setTimeout calls: " + _timerCount, ts: Date.now()}});
      _sendTelemetry();
    }}
    return _origSetTimeout.apply(window, arguments);
  }};

  // -- Monitor DOM mutations --
  if (window.MutationObserver) {{
    var observer = new MutationObserver(function(mutations) {{
      _mutationCount += mutations.length;
      if (_mutationCount % 100 === 0 && _mutationCount > 0) {{
        _sendTelemetry();
      }}
    }});
    document.addEventListener("DOMContentLoaded", function() {{
      observer.observe(document.body, {{childList: true, subtree: true, attributes: true}});
    }});
  }}

  // -- Kill switch --
  _origSetTimeout.call(window, function() {{
    _log.push({{type: "kill_switch", message: "Execution time limit reached", ts: Date.now()}});
    _sendTelemetry();
    document.body.innerHTML = "<p style='padding:20px;font-family:sans-serif;color:#c0392b'>Execution time limit reached</p>";
  }}, {KILL_SWITCH_MS});

  // Send initial telemetry after short delay
  _origSetTimeout.call(window, function() {{ _sendTelemetry(); }}, {INITIAL_TELEMETRY_DELAY_MS});
}})();
</script>
"""

_QUARANTINE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{overflow:hidden}}</style>
</head><body>
{monitoring_js}
{html}
</body></html>"""


def wrap_in_quarantine(html: str, widget_id: int) -> str:
    """Wrap widget HTML with monitoring JavaScript for quarantine execution.

    Injects interception code before the widget code that:
    - Intercepts fetch(), XMLHttpRequest, WebSocket, and EventSource calls.
    - Blocks service-worker registrations.
    - Monitors timer and DOM-mutation counts.
    - Posts telemetry to the parent window via postMessage.
    - Enforces a hard kill switch after ``KILL_SWITCH_MS``.
    """
    monitoring_js = _MONITORING_JS_TEMPLATE.format(
        widget_id=widget_id,
        TIMER_WARN_INTERVAL_COUNT=TIMER_WARN_INTERVAL_COUNT,
        TIMER_WARN_TIMEOUT_COUNT=TIMER_WARN_TIMEOUT_COUNT,
        KILL_SWITCH_MS=KILL_SWITCH_MS,
        INITIAL_TELEMETRY_DELAY_MS=INITIAL_TELEMETRY_DELAY_MS,
    )
    return _QUARANTINE_PAGE_TEMPLATE.format(monitoring_js=monitoring_js, html=html)


def create_sandbox_session(widget_id: int, browser_config: dict) -> dict:
    """Create a sandbox test session with a stable id derived from its config."""
    session_data = json.dumps(
        {"widget_id": widget_id, "config": browser_config, "ts": time.time()},
        sort_keys=True,
    )
    session_id = hashlib.sha256(session_data.encode()).hexdigest()[:SESSION_ID_HEX_LEN]

    return {
        "session_id": session_id,
        "widget_id": widget_id,
        "browser": browser_config.get("browser", "Unknown"),
        "os": browser_config.get("os", "Unknown"),
        "user_agent": browser_config.get("user_agent", ""),
        "started_at": time.time(),
        "status": "running",
    }


__all__ = [
    "BROWSER_OS_COMBOS",
    "SUSPICIOUS_DOMAIN_PATTERNS",
    "_extract_domain",
    "analyze_telemetry",
    "create_sandbox_session",
    "get_sandbox_configs",
    "wrap_in_quarantine",
]
