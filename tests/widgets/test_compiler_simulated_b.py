"""Tests for app/widgets/compiler_simulated_b.py — simulated/transpiled builders (part B)."""

from __future__ import annotations

import pytest

from app.widgets.compiler_simulated_b import (
    _build_assembly,
    _build_csharp,
    _build_golang,
    _build_rust,
    _build_visual_basic,
)

BUILDERS = [
    ("assembly", _build_assembly, "mov eax, 1"),
    ("visual_basic", _build_visual_basic, 'MsgBox "hi"'),
    ("golang", _build_golang, "package main\nfunc main(){}"),
    ("rust", _build_rust, "fn main() {}"),
    ("csharp", _build_csharp, "class C {}"),
]


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_returns_doctype_html(name, builder, snippet) -> None:
    html = builder(snippet)
    assert isinstance(html, str)
    assert html.lstrip().lower().startswith("<!doctype")
    assert len(html) > 100


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_embeds_css(name, builder, snippet) -> None:
    marker = ".sim-b-marker { color: teal; }"
    html = builder(snippet, css=marker)
    assert marker in html


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_embeds_code_contents(name, builder, snippet) -> None:
    html = builder(snippet + " ; UNIQUE_SIMB_MARKER")
    assert "UNIQUE_SIMB_MARKER" in html
