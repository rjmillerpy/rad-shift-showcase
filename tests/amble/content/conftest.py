"""Fixtures for the Amble content tests."""

import pytest

from app.amble.content import bindings


@pytest.fixture(autouse=True)
def _restore_bindings_registry():
    """`override_bindings` swaps a module-level registry and leaves restoring
    it to the caller. Do that here so one test's bindings never leak into
    the next."""
    original = bindings._replacement
    yield
    bindings.override_bindings(original)
