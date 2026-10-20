"""Tests for app/widgets/template_code_ui.py — UI-centric widget starter templates."""

from __future__ import annotations

import pytest

from app.widgets.template_code_ui import (
    DISPLAY_MOD_CODE,
    GAME_CODE,
    SOCIAL_CODE,
    TOOL_CODE,
    VIZ_CODE,
)

CONSTANTS = [
    ("GAME_CODE", GAME_CODE),
    ("VIZ_CODE", VIZ_CODE),
    ("SOCIAL_CODE", SOCIAL_CODE),
    ("TOOL_CODE", TOOL_CODE),
    ("DISPLAY_MOD_CODE", DISPLAY_MOD_CODE),
]


@pytest.mark.parametrize("name,value", CONSTANTS, ids=[c[0] for c in CONSTANTS])
def test_constant_is_non_empty_string(name, value) -> None:
    assert isinstance(value, str), f"{name} must be a string"
    assert len(value) > 100, f"{name} suspiciously short — was it truncated?"


@pytest.mark.parametrize("name,value", CONSTANTS, ids=[c[0] for c in CONSTANTS])
def test_constant_is_html_document(name, value) -> None:
    upper = value.upper()
    assert "<!DOCTYPE HTML>" in upper or "<HTML" in upper
