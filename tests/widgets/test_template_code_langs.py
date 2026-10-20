"""Tests for app/widgets/template_code_langs.py — multi-language widget starter templates."""

from __future__ import annotations

import pytest

from app.widgets.template_code_langs import (
    C_WASM_CODE,
    PHP_CODE,
    REACT_CODE,
    RUBY_CODE,
)

CONSTANTS = [
    ("REACT_CODE", REACT_CODE),
    ("C_WASM_CODE", C_WASM_CODE),
    ("RUBY_CODE", RUBY_CODE),
    ("PHP_CODE", PHP_CODE),
]


@pytest.mark.parametrize("name,value", CONSTANTS, ids=[c[0] for c in CONSTANTS])
def test_constant_is_non_empty_string(name, value) -> None:
    assert isinstance(value, str), f"{name} must be a string"
    assert len(value) > 100, f"{name} suspiciously short — was it truncated?"


@pytest.mark.parametrize("name,value", CONSTANTS, ids=[c[0] for c in CONSTANTS])
def test_constant_is_html_document(name, value) -> None:
    upper = value.upper()
    assert "<!DOCTYPE HTML>" in upper or "<HTML" in upper
