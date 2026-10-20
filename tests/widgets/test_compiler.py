"""Tests for app/widgets/compiler.py — compile source code to sandboxed HTML."""

import pytest

from app.widgets.compiler import compile_multi_panel, compile_to_html

CSS_MARKER = ".my-marker { color: red; }"


class TestCompileToHtml:
    @pytest.mark.parametrize(
        "language,snippet",
        [
            ("html", "<h1>hi</h1>"),
            ("javascript", "console.log('hi');"),
            ("python", "print('hi')"),
            ("ruby", "puts 'hi'"),
            ("php", "<?php echo 'hi'; ?>"),
            ("sql", "SELECT 1"),
            ("typescript", "const x: number = 1;"),
            ("react", "const App = () => <div>hi</div>;"),
            ("vue", "<template><div>hi</div></template>"),
            ("nodejs", "console.log('hi');"),
            ("golang", "package main"),
            ("rust", "fn main() {}"),
            ("csharp", "class C {}"),
            ("fortran", "program hello\nend program"),
            ("cobol", "IDENTIFICATION DIVISION."),
            ("c", "int main(){}"),
            ("cpp", "int main(){}"),
        ],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_every_supported_language_returns_html_document(self, language, snippet):
        html = compile_to_html(snippet, language)
        assert isinstance(html, str)
        # `html` language passes through raw code; every other language wraps it.
        if language == "html":
            assert snippet in html
        else:
            assert len(html) > 50
            assert html.lstrip().lower().startswith("<!doctype") or "<html" in html.lower()

    def test_unknown_language_falls_through_without_crash(self):
        html = compile_to_html("whatever", "klingon")
        assert isinstance(html, str)
        assert len(html) > 0

    def test_css_is_embedded(self):
        html = compile_to_html("console.log(1)", "javascript", css=CSS_MARKER)
        assert CSS_MARKER in html

    def test_html_language_wraps_raw_code(self):
        html = compile_to_html("<h1>my-heading-test</h1>", "html")
        assert "my-heading-test" in html


class TestCompileMultiPanel:
    def test_combines_html_css_js_panels(self):
        result = compile_multi_panel(
            html_panel="<div id='root'>hi</div>",
            css_panel=".my-demo { color: red; }",
            js_code="console.log('loaded');",
        )
        assert "<div id='root'>hi</div>" in result
        assert ".my-demo" in result
        assert "console.log('loaded');" in result

    def test_empty_panels_still_produce_document(self):
        result = compile_multi_panel(html_panel="", css_panel="", js_code="")
        assert "<html" in result.lower() or "<!doctype" in result.lower()

    def test_python_compute_panel_embeds_pyodide(self):
        result = compile_multi_panel(
            html_panel="<div></div>",
            css_panel="",
            js_code="",
            compute_panel="print('hi')",
            compute_language="python",
        )
        assert "pyodide" in result.lower()

    def test_sql_compute_panel_embeds_sqljs(self):
        result = compile_multi_panel(
            html_panel="<div></div>",
            css_panel="",
            js_code="",
            compute_panel="SELECT 1",
            compute_language="sql",
        )
        assert "sql.js" in result.lower() or "sql-wasm" in result.lower()
