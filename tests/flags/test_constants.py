"""app/flags/constants.py: every flag has a fallback, and fallbacks are the safe side."""

from app.flags.constants import FALLBACKS, Flag


def test_every_flag_has_a_fallback():
    assert set(FALLBACKS) == set(Flag)


def test_fallbacks_are_off():
    """When flagd can't answer: no code execution and no LLM spend."""
    assert not any(FALLBACKS.values())
