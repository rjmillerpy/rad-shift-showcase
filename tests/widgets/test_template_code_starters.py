"""app/widgets/template_code_starters.py: the state-management and WebGL starters."""

import re

import pytest

from app.widgets.template_code_starters import STATE_STORE_CODE, WEBGL_CODE
from app.widgets.templates import BUILTIN_TEMPLATES


@pytest.mark.parametrize("code", [STATE_STORE_CODE, WEBGL_CODE], ids=["state", "webgl"])
def test_no_script_is_loaded_from_elsewhere(code):
    """Self-contained: a starter never pulls an unpinned library from a CDN."""
    assert not re.search(r"<script[^>]+src=", code)


def test_the_store_changes_state_only_through_its_reducer_and_saves_it():
    assert "function reducer(state, action)" in STATE_STORE_CODE
    assert 'radshift.storage.set("state"' in STATE_STORE_CODE
    assert 'radshift.storage.get("state")' in STATE_STORE_CODE


def test_the_webgl_starter_says_when_webgl_is_missing():
    assert 'getContext("webgl"' in WEBGL_CODE
    assert "WebGL isn't available" in WEBGL_CODE


def test_both_are_offered_as_built_in_templates():
    by_name = {t["name"]: t for t in BUILTIN_TEMPLATES}
    assert by_name["State Store (Redux-style)"]["starter_code"] == STATE_STORE_CODE
    assert by_name["WebGL Starter"]["starter_code"] == WEBGL_CODE
