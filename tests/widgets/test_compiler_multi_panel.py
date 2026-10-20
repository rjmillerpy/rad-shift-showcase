"""Tests for app/widgets/compiler_multi_panel.py — HTML+CSS+JS panel composition."""

from __future__ import annotations

from app.widgets.compiler_multi_panel import compile_multi_panel


class TestCompileMultiPanel:
    def test_returns_doctype_html(self) -> None:
        html = compile_multi_panel("<h1>ok</h1>", ".x{color:red}", "console.log(1)")
        assert html.lstrip().lower().startswith("<!doctype")
        assert "<html" in html.lower()

    def test_embeds_html_panel(self) -> None:
        html = compile_multi_panel("<div>UNIQ_HTML</div>", "", "")
        assert "UNIQ_HTML" in html

    def test_embeds_css_panel(self) -> None:
        html = compile_multi_panel("", ".uniq-css-rule{color:red}", "")
        assert ".uniq-css-rule" in html

    def test_embeds_js_panel(self) -> None:
        html = compile_multi_panel("", "", "console.log('UNIQ_JS')")
        assert "UNIQ_JS" in html

    def test_python_compute_loads_pyodide(self) -> None:
        html = compile_multi_panel(
            "<div/>",
            "",
            "console.log(1)",
            compute_panel="print('hi')",
            compute_language="python",
        )
        assert "pyodide" in html.lower()
        assert "compute-ready" in html

    def test_sql_compute_loads_sqljs(self) -> None:
        html = compile_multi_panel(
            "<div/>",
            "",
            "console.log(1)",
            compute_panel="SELECT 1",
            compute_language="sql",
        )
        assert "sql.js" in html.lower() or "sql-wasm" in html.lower()
        assert "compute-ready" in html

    def test_no_compute_runs_js_immediately(self) -> None:
        html = compile_multi_panel("", "", "console.log(1)")
        assert "compute-ready" not in html
