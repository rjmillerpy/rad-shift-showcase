"""Widget security scanner.

Scans submitted widget code for:
- XSS attack patterns
- Cryptocurrency mining
- Data exfiltration attempts
- Malicious redirects
- Dangerous API usage
- Obfuscated code patterns
- Excessive resource usage indicators
"""

import logging
import re

logger = logging.getLogger(__name__)

# Each rule: (name, description, regex_pattern, severity: "critical"|"high"|"medium"|"low")
SCAN_RULES: list[tuple[str, str, str, str]] = [
    # Critical - immediate rejection
    (
        "crypto_miner",
        "Cryptocurrency mining detected",
        r"coinimp|cryptonight|coinminer|minero|webmine",
        "critical",
    ),
    ("eval_usage", "Dynamic code execution via eval()", r"\beval\s*\(", "critical"),
    ("document_cookie", "Cookie access/theft attempt", r"document\.cookie", "critical"),
    ("base64_exec", "Base64-encoded code execution", r"atob\s*\(.*\)\s*\)", "critical"),
    # High - likely malicious
    ("external_script", "Loading external scripts", r"<script[^>]+src\s*=", "high"),
    (
        "fetch_external",
        "Fetching from unknown external domains",
        r"fetch\s*\(\s*['\"]https?://(?!localhost|127\.0\.0\.1)",
        "high",
    ),
    (
        "websocket_external",
        "External WebSocket connection",
        r"new\s+WebSocket\s*\(\s*['\"]ws",
        "high",
    ),
    (
        "iframe_injection",
        "Creating iframes (escape attempt)",
        r"createElement\s*\(\s*['\"]iframe",
        "high",
    ),
    (
        "localstorage_read",
        "Reading localStorage (data access)",
        r"localStorage\.(getItem|setItem|removeItem)",
        "high",
    ),
    (
        "postmessage_parent",
        "Communicating with parent window",
        r"(parent|top|window\.opener)\.(postMessage|location)",
        "high",
    ),
    # Medium - suspicious but may be legitimate
    ("xmlhttprequest", "XMLHttpRequest usage", r"new\s+XMLHttpRequest", "medium"),
    ("form_submit", "Form submission", r"<form[^>]+action\s*=", "medium"),
    ("redirect", "Page redirect attempt", r"(window\.location|location\.href)\s*=", "medium"),
    ("geolocation", "Geolocation access", r"navigator\.geolocation", "medium"),
    ("notification", "Push notification request", r"Notification\.requestPermission", "medium"),
    # Low - informational
    ("console_log", "Console logging (debug code)", r"console\.(log|warn|error|debug)", "low"),
    ("alert_usage", "Alert/prompt/confirm usage", r"\b(alert|prompt|confirm)\s*\(", "low"),
    ("innerhtml", "innerHTML usage (XSS vector)", r"\.innerHTML\s*=", "low"),
]

SEVERITY_SCORES = {"critical": 0, "high": 20, "medium": 40, "low": 80}
PASS_THRESHOLD = 60  # Minimum score to pass


def scan_widget_code(code: str, css: str | None = None) -> dict:
    """Run all security scan rules against widget code.

    Returns:
        dict with keys:
            score (int): 0-100 security score
            passed (bool): whether the widget passes the security threshold
            issues (list[dict]): list of detected issues, each with
                rule, description, severity, line
    """
    all_issues: list[dict] = []

    # Combine code and CSS for scanning
    full_code = code
    if css:
        full_code = code + "\n" + css

    # Run each scan rule
    for name, description, pattern, severity in SCAN_RULES:
        hits = _scan_single_rule(full_code, name, description, pattern, severity)
        all_issues.extend(hits)

    # Run size check
    size_issues = check_code_size(code)
    all_issues.extend(size_issues)

    # Run obfuscation check
    obfuscation_issues = check_obfuscation(code)
    all_issues.extend(obfuscation_issues)

    score = _calculate_score(all_issues)
    passed = score >= PASS_THRESHOLD

    # Sort issues by severity (critical first)
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_issues.sort(key=lambda i: severity_order.get(i["severity"], 99))

    logger.info(
        "Security scan complete: score=%d, passed=%s, issues=%d",
        score,
        passed,
        len(all_issues),
    )

    return {
        "score": score,
        "passed": passed,
        "issues": all_issues,
    }


def _scan_single_rule(
    code: str,
    name: str,
    description: str,
    pattern: str,
    severity: str,
) -> list[dict]:
    """Check a single scan rule against code.

    Returns a list of issue dicts for each match found.
    """
    issues: list[dict] = []
    lines = code.split("\n")

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        logger.warning("Invalid regex pattern for rule %s: %s", name, exc)
        return issues

    for line_num, line in enumerate(lines, start=1):
        if compiled.search(line):
            issues.append(
                {
                    "rule": name,
                    "description": description,
                    "severity": severity,
                    "line": line_num,
                }
            )

    return issues


def _calculate_score(issues: list[dict]) -> int:
    """Calculate a security score from 0-100 based on detected issues.

    Starts at 100 and deducts points per issue based on severity.
    A single critical issue drops the score to 0.
    """
    if not issues:
        return 100

    # If any critical issue, score is 0
    severities = [i["severity"] for i in issues]
    if "critical" in severities:
        return 0

    score = 100
    deductions = {
        "high": 25,
        "medium": 10,
        "low": 3,
    }

    for issue in issues:
        sev = issue["severity"]
        score -= deductions.get(sev, 0)

    # Clamp to 0-100
    return max(0, min(100, score))


def check_code_size(code: str, max_bytes: int = 500000) -> list[dict]:
    """Check that widget code doesn't exceed the size limit.

    Args:
        code: the widget source code
        max_bytes: maximum allowed size in bytes (default 500KB)

    Returns:
        list of issue dicts if code exceeds the limit
    """
    issues: list[dict] = []
    code_bytes = len(code.encode("utf-8"))

    if code_bytes > max_bytes:
        issues.append(
            {
                "rule": "code_too_large",
                "description": f"Code size ({code_bytes} bytes) exceeds maximum ({max_bytes} bytes)",
                "severity": "high",
                "line": 0,
            }
        )
    elif code_bytes > max_bytes * 0.8:
        issues.append(
            {
                "rule": "code_near_limit",
                "description": f"Code size ({code_bytes} bytes) is near the maximum ({max_bytes} bytes)",
                "severity": "low",
                "line": 0,
            }
        )

    return issues


# ── Obfuscation heuristics ─────────────────────────────────────────────────
LONG_LINE_CHARS = 1000  # a line longer than this looks minified/packed
MANY_LONG_LINES = 3  # more than this many long lines: high severity
ESCAPES_MEDIUM = 20  # \\xNN / \\uNNNN sequences before we flag (medium)
ESCAPES_HIGH = 50  # ... and before we flag high
DENSITY_MIN_CODE_CHARS = 200  # don't judge character density on tiny snippets
MIN_ALPHANUMERIC_RATIO = 0.3  # below this share of letters/digits/spaces: flagged
REPEATED_ENCODING_MATCHES = 3  # more than this many uses of one packing trick: high

_HEX_ESCAPE = re.compile(r"\\x[0-9a-fA-F]{2}")
_UNICODE_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")

# (pattern, what it is) for common packing/encoding tricks.
_PACKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"String\.fromCharCode\s*\(", re.IGNORECASE), "String.fromCharCode encoding"),
    (re.compile(r"unescape\s*\(", re.IGNORECASE), "unescape() decoding"),
    (
        re.compile(r"Function\s*\(\s*['\"]", re.IGNORECASE),
        "Function constructor (hidden eval)",
    ),
    (
        re.compile(r"\[['\"]\w+['\"]\]\s*\(\s*\[", re.IGNORECASE),
        "Bracket-notation function calls",
    ),
]


def _issue(rule: str, description: str, severity: str, line: int = 0) -> dict:
    return {"rule": rule, "description": description, "severity": severity, "line": line}


def _long_line_issues(code: str) -> list[dict]:
    """Flag the first very long line, and again if there are many of them."""
    long_lines = [
        (number, len(line))
        for number, line in enumerate(code.split("\n"), start=1)
        if len(line) > LONG_LINE_CHARS
    ]
    if not long_lines:
        return []
    first_number, first_length = long_lines[0]
    issues = [
        _issue(
            "obfuscated_long_line",
            f"Extremely long line ({first_length} chars) suggests obfuscated code",
            "medium",
            first_number,
        )
    ]
    if len(long_lines) > MANY_LONG_LINES:
        issues.append(
            _issue(
                "obfuscated_many_long_lines",
                f"Multiple extremely long lines ({len(long_lines)}) suggest obfuscated code",
                "high",
            )
        )
    return issues


def _escape_sequence_issues(code: str) -> list[dict]:
    total_escapes = len(_HEX_ESCAPE.findall(code)) + len(_UNICODE_ESCAPE.findall(code))
    if total_escapes > ESCAPES_HIGH:
        description = f"Excessive escape sequences ({total_escapes}) suggest obfuscated code"
        return [_issue("obfuscated_escape_sequences", description, "high")]
    if total_escapes > ESCAPES_MEDIUM:
        description = f"Many escape sequences ({total_escapes}) may indicate obfuscated code"
        return [_issue("obfuscated_escape_sequences", description, "medium")]
    return []


def _char_density_issues(code: str) -> list[dict]:
    """Flag code that is mostly punctuation (only judged on non-trivial code)."""
    if len(code) <= DENSITY_MIN_CODE_CHARS:
        return []
    readable_chars = sum(1 for char in code if char.isalnum() or char.isspace())
    ratio = readable_chars / len(code)
    if ratio >= MIN_ALPHANUMERIC_RATIO:
        return []
    description = f"Low alphanumeric ratio ({ratio:.1%}) suggests obfuscated code"
    return [_issue("obfuscated_char_density", description, "medium")]


def _packed_code_issues(code: str) -> list[dict]:
    issues: list[dict] = []
    for pattern, what in _PACKED_PATTERNS:
        occurrences = len(pattern.findall(code))
        if occurrences > REPEATED_ENCODING_MATCHES:
            description = f"Repeated {what} pattern ({occurrences} occurrences)"
            issues.append(_issue("obfuscated_encoding", description, "high"))
        elif occurrences:
            issues.append(_issue("obfuscated_encoding", f"{what} detected", "medium"))
    return issues


def check_obfuscation(code: str) -> list[dict]:
    """Detect heavily obfuscated code patterns.

    Checks for:
    - Very long lines that suggest minified/obfuscated code
    - Excessive hex/unicode escape sequences
    - Unusual character density (high ratio of non-alphanumeric characters)
    - Packed/encoded code (String.fromCharCode, unescape, Function constructor)
    """
    return [
        *_long_line_issues(code),
        *_escape_sequence_issues(code),
        *_char_density_issues(code),
        *_packed_code_issues(code),
    ]
