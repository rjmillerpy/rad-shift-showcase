"""Tests for app/plugins.py — choosing and pinning the edition."""

from dataclasses import replace
from importlib.metadata import EntryPoint, EntryPoints
from unittest.mock import patch

import pytest

from app import plugins
from app.baseline import EDITION as PUBLIC_EDITION
from app.generators.platforms.base import PlatformAdapter
from app.plugins import EditionError, edition, use_edition

ENTRY_POINTS = "app.plugins.entry_points"


class _Adapter(PlatformAdapter):
    def __init__(self, name: str) -> None:
        self.platform = name

    def validate_config(self, platform_config):
        pass

    def fetch_items(self, platform_config, max_items):
        return []


def _entry_points(*values: str) -> EntryPoints:
    return EntryPoints(
        EntryPoint(name=f"ep{i}", value=value, group=plugins.ENTRY_POINT_GROUP)
        for i, value in enumerate(values)
    )


class TestEditionValidation:
    @pytest.mark.parametrize("name", ["", "web"], ids=["empty", "reserved-web"])
    def test_rejects_bad_adapter_names(self, name):
        with pytest.raises(EditionError):
            replace(PUBLIC_EDITION, platform_adapters=(_Adapter(name),))

    def test_rejects_duplicate_platforms(self):
        with pytest.raises(EditionError, match="duplicate"):
            replace(PUBLIC_EDITION, platform_adapters=(_Adapter("a"), _Adapter("a")))


class TestLoad:
    def test_public_pin_ignores_an_installed_private_package(self):
        with patch(ENTRY_POINTS, return_value=_entry_points("app.baseline:EDITION")) as found:
            assert plugins._load(plugins.PUBLIC) is PUBLIC_EDITION
        found.assert_not_called()

    def test_unpinned_falls_back_to_public_without_a_private_package(self):
        with patch(ENTRY_POINTS, return_value=_entry_points()):
            assert plugins._load(None) is PUBLIC_EDITION

    def test_private_pin_fails_loudly_without_a_private_package(self):
        with patch(ENTRY_POINTS, return_value=_entry_points()), pytest.raises(EditionError):
            plugins._load(plugins.PRIVATE)

    def test_unpinned_uses_the_registered_edition(self):
        with patch(ENTRY_POINTS, return_value=_entry_points("app.baseline:EDITION")):
            assert plugins._load(None) is PUBLIC_EDITION

    def test_unknown_pin_is_rejected(self):
        with pytest.raises(EditionError, match="RADSHIFT_EDITION"):
            plugins._load("enterprise")

    def test_two_registered_editions_are_ambiguous(self):
        found = _entry_points("app.baseline:EDITION", "app.baseline:EDITION")
        with (
            patch(ENTRY_POINTS, return_value=found),
            pytest.raises(EditionError, match="more than one"),
        ):
            plugins._load(None)

    def test_entry_point_must_be_an_edition(self):
        with (
            patch(ENTRY_POINTS, return_value=_entry_points("app.plugins:PUBLIC")),
            pytest.raises(EditionError, match="not an Edition"),
        ):
            plugins._load(None)


class TestUseEdition:
    def test_overrides_and_restores(self):
        other = replace(PUBLIC_EDITION, name="other")
        before = edition()
        with use_edition(other):
            assert edition() is other
        assert edition() is before
