"""Tests for app/widgets/compiler_base.py — shared primitives for builders."""

from __future__ import annotations

from app.widgets.compiler_base import _TERMINAL_STYLES, _escape, _wrap_runtime


class TestWrapRuntime:
    def test_returns_doctype_html(self) -> None:
        html = _wrap_runtime("Foo", "", "print('x');")
        assert html.lstrip().lower().startswith("<!doctype")
        assert "<html" in html.lower()

    def test_embeds_interpreter_script_when_url_given(self) -> None:
        html = _wrap_runtime("Foo", "https://cdn/example.js", "print('x');")
        assert 'src="https://cdn/example.js"' in html

    def test_omits_script_tag_when_url_empty(self) -> None:
        html = _wrap_runtime("Foo", "", "print('x');")
        assert "<script src=" not in html

    def test_css_is_embedded_in_style_block(self) -> None:
        html = _wrap_runtime("Foo", "", "print('x');", css=".custom-hook { color: lime; }")
        assert ".custom-hook" in html

    def test_runner_js_is_included(self) -> None:
        html = _wrap_runtime("Foo", "", "print('UNIQUE_MARKER_BODY');")
        assert "UNIQUE_MARKER_BODY" in html


class TestEscape:
    def test_returns_json_encoded_string(self) -> None:
        assert _escape("hello") == '"hello"'

    def test_escapes_quotes_and_newlines(self) -> None:
        result = _escape('line1\n"quoted"')
        assert "\\n" in result
        assert '\\"' in result


class TestTerminalStyles:
    def test_is_non_empty_string(self) -> None:
        assert isinstance(_TERMINAL_STYLES, str)
        assert "body" in _TERMINAL_STYLES
        assert "#output" in _TERMINAL_STYLES
