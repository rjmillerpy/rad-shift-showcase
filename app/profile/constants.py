"""Shared constants for the profile domain.

Defaults for the four settings surfaces (algo, bubble, chronicle, agora) live
here so schema, service, and views all reference the same source of truth.

The algo weight defaults are derived from `app.posts.feeds.AlgoWeights` so the
recommender-side defaults and the settings-page defaults cannot drift.
"""

from dataclasses import asdict

from app.posts.feeds import AlgoWeights

# ── Profile picture upload ─────────────────────────────────────────────────

ALLOWED_PROFILE_PIC_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
PROFILE_PIC_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}
PROFILE_PIC_S3_KEY_PREFIX = "profile_pictures"


# ── Profile response ───────────────────────────────────────────────────────

MAX_USER_POSTS_ON_PROFILE = 100
MAX_USERNAME_PATH_LEN = 80


# ── Settings defaults ──────────────────────────────────────────────────────


def _algo_weight_defaults() -> dict:
    """Extract the weight portion of the algo settings from `AlgoWeights`."""
    weights = asdict(AlgoWeights())
    # AlgoWeights fields don't have the `_weight` suffix used at the API layer.
    return {f"{k}_weight": v for k, v in weights.items()}


DEFAULT_ALGO_SETTINGS: dict = {
    "engagement_enabled": True,
    **_algo_weight_defaults(),
    "randomness": 0.1,
    "interest_adaptation": 0.5,
    "category_diversity": 0.5,
    "show_followed_boost": True,
    "hide_seen_posts": False,
    "preferred_categories": [],
    "blocked_categories": [],
    "slop_filter": "hide",
    "slop_threshold": 0,
}


DEFAULT_BUBBLE_SETTINGS: dict = {
    "animation_speed": 0.4,
    "bubble_density": 16,
    "show_media_previews": True,
    "show_avatars": True,
    "auto_drill_cooldown": 2000,
    "color_saturation": 1.0,
    "show_connection_lines": True,
    "custom_topics": [],
    "hidden_topics": [],
    "goal_prompt_enabled": True,
    "focus_timer_enabled": True,
    "depth_indicator_enabled": True,
}


DEFAULT_CHRONICLE_SETTINGS: dict = {
    "posts_per_page": 8,
    "narrative_style": "literary",
    "show_media_inline": True,
    "show_engagement_in_tooltip": True,
    "cache_duration_hours": 1,
    "title_prompt_enabled": True,
    "auto_advance": False,
    "font_size": 16,
    "line_height": 1.8,
    "theme": "parchment",
}


DEFAULT_AGORA_SETTINGS: dict = {
    "posts_per_page": 20,
    "sort_by": "algo",
    "show_avatars": True,
    "show_signatures": True,
    "show_post_counts": True,
    "show_join_dates": True,
    "highlight_op": True,
    "compact_mode": False,
    "theme": "classic",
}
