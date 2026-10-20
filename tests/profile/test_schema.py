"""Tests for profile Pydantic schemas."""

import pytest

from app.profile.schema import (
    AgoraSettingsRequest,
    AlgoSettingsRequest,
    BubbleSettingsRequest,
    ChronicleSettingsRequest,
    ProfileData,
)


class TestProfileData:
    def test_all_optional(self):
        data = ProfileData()
        assert data.bio is None
        assert data.profile_picture_url is None

    def test_with_values(self):
        data = ProfileData(bio="Hello", profile_picture_url="https://example.com/pic.jpg")
        assert data.bio == "Hello"
        assert data.profile_picture_url == "https://example.com/pic.jpg"

    def test_partial_update(self):
        data = ProfileData(bio="Just bio")
        assert data.bio == "Just bio"
        assert data.profile_picture_url is None


class TestAlgoSettingsRequest:
    def test_defaults(self):
        settings = AlgoSettingsRequest()
        assert settings.engagement_enabled is None
        assert settings.like_weight is None
        assert settings.recency_weight is None
        assert settings.preferred_categories is None
        assert settings.slop_filter is None

    @pytest.mark.parametrize(
        "field,value",
        [
            ("like_weight", 0.0),
            ("like_weight", 1.0),
            ("like_weight", 100.0),
            ("recency_weight", 0.0),
            ("randomness", 0.5),
            ("slop_threshold", 0),
            ("slop_threshold", 100),
        ],
    )
    def test_weight_boundary_values(self, field, value):
        settings = AlgoSettingsRequest(**{field: value})
        assert getattr(settings, field) == value

    @pytest.mark.parametrize(
        "field,value",
        [
            ("engagement_enabled", True),
            ("engagement_enabled", False),
            ("show_followed_boost", True),
            ("hide_seen_posts", False),
        ],
    )
    def test_boolean_fields(self, field, value):
        settings = AlgoSettingsRequest(**{field: value})
        assert getattr(settings, field) == value

    def test_list_fields(self):
        settings = AlgoSettingsRequest(
            preferred_categories=["tech", "art"],
            blocked_categories=["spam"],
        )
        assert settings.preferred_categories == ["tech", "art"]
        assert settings.blocked_categories == ["spam"]


class TestBubbleSettingsRequest:
    def test_defaults(self):
        settings = BubbleSettingsRequest()
        assert settings.animation_speed is None
        assert settings.bubble_density is None

    @pytest.mark.parametrize(
        "field,value",
        [
            ("animation_speed", 0.0),
            ("animation_speed", 1.0),
            ("bubble_density", 1),
            ("bubble_density", 100),
            ("color_saturation", 0.0),
            ("auto_drill_cooldown", 0),
        ],
    )
    def test_numeric_boundaries(self, field, value):
        settings = BubbleSettingsRequest(**{field: value})
        assert getattr(settings, field) == value


class TestChronicleSettingsRequest:
    def test_defaults(self):
        settings = ChronicleSettingsRequest()
        assert settings.posts_per_page is None
        assert settings.narrative_style is None

    @pytest.mark.parametrize("theme", ["parchment", "dark", "custom"])
    def test_theme_values(self, theme):
        settings = ChronicleSettingsRequest(theme=theme)
        assert settings.theme == theme


class TestAgoraSettingsRequest:
    def test_defaults(self):
        settings = AgoraSettingsRequest()
        assert settings.posts_per_page is None
        assert settings.sort_by is None

    @pytest.mark.parametrize("sort_by", ["algo", "newest", "oldest", "popular"])
    def test_sort_options(self, sort_by):
        settings = AgoraSettingsRequest(sort_by=sort_by)
        assert settings.sort_by == sort_by
