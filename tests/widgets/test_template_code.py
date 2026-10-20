"""Tests for app/widgets/template_code.py — starter-code constants exist and are non-empty.

These are static strings that ship with the product. The tests guard against
accidental deletion / truncation when someone edits this file.
"""

import pytest

from app.widgets import template_code

EXPECTED_CONSTANTS = [
    "GAME_CODE",
    "API_CODE",
    "LAMBDA_CODE_PY",
    "LAMBDA_CODE_NODE",
    "DB_CONNECTOR_CODE",
    "VIZ_CODE",
    "SOCIAL_CODE",
    "TOOL_CODE",
    "DISPLAY_MOD_CODE",
    "REACT_CODE",
    "C_WASM_CODE",
    "RUBY_CODE",
    "PHP_CODE",
]


class TestTemplateCodeConstants:
    @pytest.mark.parametrize("name", EXPECTED_CONSTANTS)
    def test_constant_exists_and_is_non_empty_string(self, name):
        value = getattr(template_code, name, None)
        assert isinstance(value, str), f"{name} missing or wrong type"
        assert len(value) > 100, f"{name} suspiciously short — was it truncated?"

    def test_html_template_is_valid_html(self):
        """Sanity: at least one template should be a complete HTML document."""
        assert (
            "<!DOCTYPE html>" in template_code.GAME_CODE.upper()
            or "<HTML" in template_code.GAME_CODE.upper()
        )
