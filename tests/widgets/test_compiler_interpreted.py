"""Tests for app/widgets/compiler_interpreted.py — CDN-hosted interpreter wrappers."""

from __future__ import annotations

import pytest

from app.widgets.compiler_interpreted import (
    _build_lua,
    _build_php,
    _build_python,
    _build_ruby,
    _build_sql,
)

BUILDERS = [
    ("python", _build_python, "print('hi')"),
    ("ruby", _build_ruby, "puts 'hi'"),
    ("php", _build_php, "echo 'hi';"),
    ("sql", _build_sql, "SELECT 1"),
    ("lua", _build_lua, "print('hi')"),
]


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_returns_doctype_html(name, builder, snippet) -> None:
    html = builder(snippet)
    assert isinstance(html, str)
    assert html.lstrip().lower().startswith("<!doctype")
    assert "<html" in html.lower()
    assert len(html) > 100


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_embeds_user_code(name, builder, snippet) -> None:
    # _escape JSON-encodes the code, so the literal substring is present.
    html = builder(snippet)
    assert "UNIQUE_MARKER_X" not in html  # sanity
    html_with_marker = builder(snippet + " # UNIQUE_MARKER_X")
    assert "UNIQUE_MARKER_X" in html_with_marker


@pytest.mark.parametrize("name,builder,snippet", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_embeds_css(name, builder, snippet) -> None:
    marker = ".interp-marker-xyz { color: lime; }"
    html = builder(snippet, css=marker)
    assert marker in html
