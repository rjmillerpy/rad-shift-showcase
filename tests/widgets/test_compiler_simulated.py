"""Tests for app/widgets/compiler_simulated.py — simulated/transpiled builders (part A)."""

from __future__ import annotations

import pytest

from app.widgets.compiler_simulated import (
    _build_basic,
    _build_cobol,
    _build_cpp,
    _build_fortran,
    _build_nodejs,
    _build_simulated,
    _build_typescript,
)

BUILDERS = [
    ("nodejs", _build_nodejs, "console.log('hi')"),
    ("cpp", _build_cpp, "int main(){return 0;}"),
    ("typescript", _build_typescript, "const x: number = 1;"),
    ("basic", _build_basic, '10 PRINT "HI"'),
    ("fortran", _build_fortran, "PRINT *, 'hi'"),
    ("cobol", _build_cobol, "DISPLAY 'hi'."),
]


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_returns_doctype_html(name, builder, snippet) -> None:
    html = builder(snippet)
    assert isinstance(html, str)
    assert html.lstrip().lower().startswith("<!doctype")
    assert len(html) > 100


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_embeds_css(name, builder, snippet) -> None:
    marker = ".sim-a-marker { color: coral; }"
    html = builder(snippet, css=marker)
    assert marker in html


def test_build_simulated_embeds_language_name() -> None:
    html = _build_simulated("code-here", "Elixir")
    assert "Elixir" in html


def test_build_simulated_returns_doctype_html() -> None:
    html = _build_simulated("code", "Kotlin")
    assert html.lstrip().lower().startswith("<!doctype")
