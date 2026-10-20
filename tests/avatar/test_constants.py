"""Tests for app/avatar/constants.py — invariants on the shared constants."""

from app.avatar import constants


class TestNumericConstants:
    def test_avatar_size_positive(self):
        assert constants.AVATAR_SIZE > 0

    def test_hash_seed_versioned(self):
        assert constants.HASH_SEED.startswith("radshift-avatar-")

    def test_bg_saturation_bounds_within_hsl(self):
        upper = constants.BG_SATURATION_MIN + constants.BG_SATURATION_RANGE
        assert 0 <= constants.BG_SATURATION_MIN < upper <= 100

    def test_bg_lightness_bounds_within_hsl(self):
        upper = constants.BG_LIGHTNESS_MIN + constants.BG_LIGHTNESS_RANGE
        assert 0 <= constants.BG_LIGHTNESS_MIN < upper <= 100

    def test_silhouette_saturation_bounds_within_hsl(self):
        upper = constants.SILHOUETTE_SATURATION_MIN + constants.SILHOUETTE_SATURATION_RANGE
        assert 0 <= constants.SILHOUETTE_SATURATION_MIN < upper <= 100

    def test_silhouette_lightness_bounds_within_hsl(self):
        upper = constants.SILHOUETTE_LIGHTNESS_MIN + constants.SILHOUETTE_LIGHTNESS_RANGE
        assert 0 <= constants.SILHOUETTE_LIGHTNESS_MIN < upper <= 100

    def test_hue_wheel_full_circle(self):
        assert constants.HUE_DEGREES == 360

    def test_byte_modulo_matches_byte_range(self):
        assert constants.BYTE_MODULO == 256

    def test_preview_caps_positive(self):
        assert constants.MAX_PREVIEW_USERNAME_LEN > 0
        assert constants.MAX_PREVIEW_EMAIL_LEN > 0
