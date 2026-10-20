"""Tests for app/widgets/compiler_native.py — HTML, JavaScript, and CSS builders."""

from __future__ import annotations

import pytest

from app.widgets.compiler_native import _build_css, _build_html, _build_javascript

CSS_MARKER = ".test-marker-native { color: magenta; }"


class TestBuildHtml:
    def test_returns_raw_code_when_no_css(self) -> None:
        html = _build_html("<h1>hello</h1>")
        assert html == "<h1>hello</h1>"

    def test_injects_style_tag_when_css_given(self) -> None:
        html = _build_html("<h1>hi</h1>", css=CSS_MARKER)
        assert CSS_MARKER in html

    def test_injects_style_before_head_close_when_head_present(self) -> None:
        html = _build_html("<head></head><body>x</body>", css=CSS_MARKER)
        assert f"<style>{CSS_MARKER}</style></head>" in html


class TestBuildJavascript:
    def test_returns_doctype_html(self) -> None:
        html = _build_javascript("console.log('ok');")
        assert html.lstrip().lower().startswith("<!doctype")
        assert "<html" in html.lower()

    def test_embeds_user_code(self) -> None:
        html = _build_javascript("console.log('UNIQUE_JS_MARKER');")
        assert "UNIQUE_JS_MARKER" in html

    def test_css_is_embedded(self) -> None:
        html = _build_javascript("console.log('ok');", css=CSS_MARKER)
        assert CSS_MARKER in html


class TestBuildCss:
    def test_returns_doctype_html(self) -> None:
        html = _build_css("body { color: red; }")
        assert html.lstrip().lower().startswith("<!doctype")
        assert "<html" in html.lower()

    def test_embeds_user_css_in_head(self) -> None:
        html = _build_css(".my-css-rule { color: green; }")
        assert ".my-css-rule" in html

    def test_demo_dom_is_present(self) -> None:
        html = _build_css(".x { color: blue; }")
        # The builder injects a fixed preview DOM so users see their CSS applied.
        assert "CSS Preview" in html


@pytest.mark.parametrize("builder", [_build_javascript, _build_css])
def test_output_is_non_empty_string(builder) -> None:
    html = builder("sample input")
    assert isinstance(html, str)
    assert len(html) > 50
