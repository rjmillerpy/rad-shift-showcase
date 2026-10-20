"""Tests for app/profile/constants.py — settings-default invariants."""

from app.posts.feeds import AlgoWeights
from app.profile import constants


class TestPictureUpload:
    def test_content_types_cover_every_allowed(self):
        missing = constants.ALLOWED_PROFILE_PIC_EXTENSIONS - set(
            constants.PROFILE_PIC_CONTENT_TYPES
        )
        assert missing == set()

    def test_no_extra_content_types(self):
        extra = set(constants.PROFILE_PIC_CONTENT_TYPES) - constants.ALLOWED_PROFILE_PIC_EXTENSIONS
        assert extra == set()

    def test_s3_prefix_no_leading_slash(self):
        assert not constants.PROFILE_PIC_S3_KEY_PREFIX.startswith("/")


class TestListCaps:
    def test_max_user_posts_positive(self):
        assert constants.MAX_USER_POSTS_ON_PROFILE > 0

    def test_username_path_cap_matches_auth(self):
        from app.auth.constants import MAX_USERNAME_LEN

        # The profile-view path cap should be at least as big as the auth
        # username cap so no legitimately-created user is unreachable.
        assert constants.MAX_USERNAME_PATH_LEN >= MAX_USERNAME_LEN


class TestSettingsDefaults:
    def test_all_defaults_are_dicts(self):
        for d in (
            constants.DEFAULT_ALGO_SETTINGS,
            constants.DEFAULT_BUBBLE_SETTINGS,
            constants.DEFAULT_CHRONICLE_SETTINGS,
            constants.DEFAULT_AGORA_SETTINGS,
        ):
            assert isinstance(d, dict)
            assert d, "defaults dict should not be empty"

    def test_algo_weights_match_recommender_defaults(self):
        """The settings-page algo weight defaults must equal the recommender
        defaults (rule 16 — one source of truth). Any drift breaks user
        expectations when their settings are 'reset to defaults'."""
        weights = AlgoWeights()
        for name in ("like", "repost", "share", "laugh", "save", "slop", "recency"):
            key = f"{name}_weight"
            assert constants.DEFAULT_ALGO_SETTINGS[key] == getattr(weights, name)
