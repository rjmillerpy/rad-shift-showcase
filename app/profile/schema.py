"""Pydantic request and response schemas for profile endpoints.

The four `*SettingsRequest` models mirror the keys of `DEFAULT_*_SETTINGS` in
constants.py and are wired to the corresponding PUT endpoints so the API
boundary rejects unknown fields instead of silently ignoring them.
"""

from typing import Literal

from pydantic import BaseModel

from app.common.schema import FrozenModel
from app.posts.schema import PostResponse

SlopFilterMode = Literal["hide", "dim", "show", "only"]


class ProfileData(BaseModel):
    bio: str | None = None
    profile_picture_url: str | None = None


class AlgoSettingsRequest(BaseModel):
    engagement_enabled: bool | None = None
    like_weight: float | None = None
    repost_weight: float | None = None
    share_weight: float | None = None
    laugh_weight: float | None = None
    save_weight: float | None = None
    slop_weight: float | None = None
    recency_weight: float | None = None
    randomness: float | None = None
    interest_adaptation: float | None = None
    category_diversity: float | None = None
    show_followed_boost: bool | None = None
    hide_seen_posts: bool | None = None
    preferred_categories: list[str] | None = None
    blocked_categories: list[str] | None = None
    slop_filter: SlopFilterMode | None = None
    slop_threshold: int | None = None


class BubbleSettingsRequest(BaseModel):
    animation_speed: float | None = None
    bubble_density: int | None = None
    show_media_previews: bool | None = None
    show_avatars: bool | None = None
    auto_drill_cooldown: int | None = None
    color_saturation: float | None = None
    show_connection_lines: bool | None = None
    custom_topics: list[str] | None = None
    hidden_topics: list[str] | None = None
    goal_prompt_enabled: bool | None = None
    focus_timer_enabled: bool | None = None
    depth_indicator_enabled: bool | None = None


class ChronicleSettingsRequest(BaseModel):
    posts_per_page: int | None = None
    narrative_style: str | None = None
    show_media_inline: bool | None = None
    show_engagement_in_tooltip: bool | None = None
    cache_duration_hours: int | None = None
    title_prompt_enabled: bool | None = None
    auto_advance: bool | None = None
    font_size: int | None = None
    line_height: float | None = None
    theme: str | None = None


class AgoraSettingsRequest(BaseModel):
    posts_per_page: int | None = None
    sort_by: str | None = None
    show_avatars: bool | None = None
    show_signatures: bool | None = None
    show_post_counts: bool | None = None
    show_join_dates: bool | None = None
    highlight_op: bool | None = None
    compact_mode: bool | None = None
    theme: str | None = None


# ── Responses ──────────────────────────────────────────────────────────────
# Each *SettingsResponse is the full, resolved settings object (defaults
# overlaid with what the user saved), so every field is required.
# tests/profile/test_schema.py keeps the request models, these and the
# DEFAULT_*_SETTINGS dicts on the same set of keys.


class ProfileResponse(FrozenModel):
    username: str
    bio: str | None
    profile_picture_url: str | None
    posts: list[PostResponse]


class ProfilePictureResponse(FrozenModel):
    message: str
    url: str


class AlgoSettingsResponse(FrozenModel):
    engagement_enabled: bool
    like_weight: float
    repost_weight: float
    share_weight: float
    laugh_weight: float
    save_weight: float
    slop_weight: float
    recency_weight: float
    randomness: float
    interest_adaptation: float
    category_diversity: float
    show_followed_boost: bool
    hide_seen_posts: bool
    preferred_categories: list[str]
    blocked_categories: list[str]
    slop_filter: SlopFilterMode
    slop_threshold: int


class BubbleSettingsResponse(FrozenModel):
    animation_speed: float
    bubble_density: int
    show_media_previews: bool
    show_avatars: bool
    auto_drill_cooldown: int
    color_saturation: float
    show_connection_lines: bool
    custom_topics: list[str]
    hidden_topics: list[str]
    goal_prompt_enabled: bool
    focus_timer_enabled: bool
    depth_indicator_enabled: bool


class ChronicleSettingsResponse(FrozenModel):
    posts_per_page: int
    narrative_style: str
    show_media_inline: bool
    show_engagement_in_tooltip: bool
    cache_duration_hours: int
    title_prompt_enabled: bool
    auto_advance: bool
    font_size: int
    line_height: float
    theme: str


class AgoraSettingsResponse(FrozenModel):
    posts_per_page: int
    sort_by: str
    show_avatars: bool
    show_signatures: bool
    show_post_counts: bool
    show_join_dates: bool
    highlight_op: bool
    compact_mode: bool
    theme: str
