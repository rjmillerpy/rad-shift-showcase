"""Tests for app/widgets/template_code_data.py — data/API widget starter templates."""

from __future__ import annotations

import pytest

from app.widgets.template_code_data import (
    API_CODE,
    DB_CONNECTOR_CODE,
    LAMBDA_CODE_NODE,
    LAMBDA_CODE_PY,
)

CONSTANTS = [
    ("API_CODE", API_CODE),
    ("LAMBDA_CODE_PY", LAMBDA_CODE_PY),
    ("LAMBDA_CODE_NODE", LAMBDA_CODE_NODE),
    ("DB_CONNECTOR_CODE", DB_CONNECTOR_CODE),
]


@pytest.mark.parametrize("name,value", CONSTANTS, ids=[c[0] for c in CONSTANTS])
def test_constant_is_non_empty_string(name, value) -> None:
    assert isinstance(value, str), f"{name} must be a string"
    assert len(value) > 100, f"{name} suspiciously short — was it truncated?"


@pytest.mark.parametrize("name,value", CONSTANTS, ids=[c[0] for c in CONSTANTS])
def test_constant_is_html_document(name, value) -> None:
    upper = value.upper()
    assert "<!DOCTYPE HTML>" in upper or "<HTML" in upper
