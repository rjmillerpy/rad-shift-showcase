"""Tests for app/avatar/generator.py — deterministic avatar generation.

Silhouette dataset assertions live in test_silhouettes.py.
Cross-cutting signup→avatar flow lives in tests/integration/test_signup_avatar.py.
"""

import pytest

from app.avatar.constants import HUE_DEGREES
from app.avatar.generator import (
    _extract_colors,
    _hash_user,
    _hsl_to_rgb,
    _hue_from_byte,
    _select_animal,
    generate_avatar,
)
from app.avatar.silhouettes import ANIMAL_COUNT


class TestHashUser:
    def test_deterministic(self):
        """Pinned, not just compared with itself: a changed hash would give every user a new avatar."""
        assert _hash_user("alice", "alice@test.com").hex() == (
            "caa1d0897b056e86f248d2ffde733ebc988528628a868d934c990a9691ebc1fe"
        )

    def test_different_users_produce_different_hash(self):
        assert _hash_user("alice", "alice@test.com") != _hash_user("bob", "bob@test.com")

    def test_case_insensitive(self):
        assert _hash_user("Alice", "Alice@Test.com") == _hash_user("alice", "alice@test.com")

    def test_returns_32_bytes(self):
        assert len(_hash_user("user", "u@t.com")) == 32


class TestHueFromByte:
    @pytest.mark.parametrize(
        "byte,expected",
        [(0, 0), (128, 180), (255, 358)],
        ids=["zero", "midpoint", "max"],
    )
    def test_maps_byte_to_hue(self, byte, expected):
        assert _hue_from_byte(byte) == expected

    def test_never_exceeds_hue_wheel(self):
        for byte in range(256):
            assert 0 <= _hue_from_byte(byte) < HUE_DEGREES


class TestExtractColors:
    def test_returns_three_rgb_tuples_in_channel_range(self):
        h = _hash_user("test", "t@t.com")
        bg1, bg2, sil = _extract_colors(h)
        for color in (bg1, bg2, sil):
            assert len(color) == 3
            assert all(0 <= c <= 255 for c in color)

    def test_deterministic(self):
        """Pinned: the same user keeps the same colours across releases."""
        assert _extract_colors(_hash_user("test", "t@t.com")) == (
            (47, 135, 81),
            (140, 97, 38),
            (236, 250, 224),
        )


class TestSelectAnimal:
    def test_in_range(self):
        assert 0 <= _select_animal(_hash_user("test", "t@t.com")) < ANIMAL_COUNT

    @pytest.mark.parametrize(
        "username,email,animal",
        [
            ("alice", "a@t.com", 15),
            ("bob", "b@t.com", 18),
            ("charlie", "c@t.com", 4),
            ("diana", "d@t.com", 13),
        ],
        ids=["alice", "bob", "charlie", "diana"],
    )
    def test_deterministic_per_user(self, username, email, animal):
        """Pinned: the same user keeps the same animal across releases."""
        assert _select_animal(_hash_user(username, email)) == animal


class TestHslToRgb:
    @pytest.mark.parametrize(
        "h,s,lightness,expected",
        [
            (0, 100, 50, (255, 0, 0)),
            (120, 100, 50, (0, 255, 0)),
            (240, 100, 50, (0, 0, 255)),
            (0, 0, 0, (0, 0, 0)),
            (0, 0, 100, (255, 255, 255)),
        ],
        ids=["red", "green", "blue", "black", "white"],
    )
    def test_known_colors(self, h, s, lightness, expected):
        assert _hsl_to_rgb(h, s, lightness) == expected


class TestGenerateAvatar:
    def test_returns_png_bytes(self):
        data = generate_avatar("test", "t@t.com")
        assert isinstance(data, bytes)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_deterministic(self):
        # Two separate renders, compared byte for byte (exact bytes depend on
        # the Pillow version, so they aren't pinned; the inputs above are).
        first = generate_avatar("alice", "a@t.com")
        second = generate_avatar("alice", "a@t.com")
        assert first == second

    def test_different_users_produce_different_avatars(self):
        assert generate_avatar("alice", "a@t.com") != generate_avatar("bob", "b@t.com")

    def test_reasonable_size(self):
        data = generate_avatar("test", "t@t.com")
        assert 100 < len(data) < 500_000
