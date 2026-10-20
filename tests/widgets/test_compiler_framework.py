"""Tests for app/widgets/compiler_framework.py — React and Vue builders."""

from __future__ import annotations

import pytest

from app.widgets.compiler_framework import _build_react, _build_vue

BUILDERS = [
    ("react", _build_react, "const App = () => <div>hi</div>;"),
    ("vue", _build_vue, "Vue.createApp({}).mount('#app')"),
]


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_returns_doctype_html(name, builder, snippet) -> None:
    html = builder(snippet)
    assert isinstance(html, str)
    assert html.lstrip().lower().startswith("<!doctype")
    assert "<html" in html.lower()


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_embeds_css(name, builder, snippet) -> None:
    marker = ".fw-marker-123 { color: gold; }"
    html = builder(snippet, css=marker)
    assert marker in html


def test_react_loads_react_cdn() -> None:
    html = _build_react("const App = () => <div/>;")
    assert "react" in html.lower()
    assert "root" in html


def test_vue_loads_vue_cdn() -> None:
    html = _build_vue("Vue.createApp({}).mount('#app')")
    assert "vue" in html.lower()
    assert 'id="app"' in html


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_user_code_appears_in_output(name, builder, snippet) -> None:
    html = builder(snippet + " /* UNIQUE_FW_MARKER */")
    assert "UNIQUE_FW_MARKER" in html
