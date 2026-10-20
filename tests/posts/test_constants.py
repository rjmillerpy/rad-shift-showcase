"""Tests for app/posts/constants.py — invariants on shared post constants."""

from app.posts import constants


class TestFileSizeCaps:
    def test_bytes_matches_mb(self):
        assert constants.MAX_FILE_SIZE_BYTES == constants.MAX_FILE_SIZE_MB * 1024 * 1024

    def test_bytes_positive(self):
        assert constants.MAX_FILE_SIZE_BYTES > 0


class TestTextCaps:
    def test_max_post_text_positive(self):
        assert constants.MAX_POST_TEXT_CHARS > 0

    def test_tag_results_positive(self):
        assert constants.MAX_TAG_RESULTS > 0


class TestExtensionAllowlists:
    def test_no_extension_repeats_across_kinds(self):
        buckets = [
            constants.ALLOWED_IMAGE_EXTENSIONS,
            constants.ALLOWED_VIDEO_EXTENSIONS,
            constants.ALLOWED_AUDIO_EXTENSIONS,
            constants.ALLOWED_DOCUMENT_EXTENSIONS,
            constants.ALLOWED_ARCHIVE_EXTENSIONS,
        ]
        total = sum(len(b) for b in buckets)
        combined = set().union(*buckets)
        assert len(combined) == total, "an extension appears in more than one bucket"

    def test_allowed_is_the_union(self):
        assert constants.ALLOWED_EXTENSIONS == (
            constants.ALLOWED_IMAGE_EXTENSIONS
            | constants.ALLOWED_VIDEO_EXTENSIONS
            | constants.ALLOWED_AUDIO_EXTENSIONS
            | constants.ALLOWED_DOCUMENT_EXTENSIONS
            | constants.ALLOWED_ARCHIVE_EXTENSIONS
        )

    def test_extension_content_types_cover_every_allowed(self):
        missing = constants.ALLOWED_EXTENSIONS - set(constants.EXTENSION_CONTENT_TYPES)
        assert missing == set(), f"missing content types for: {missing}"

    def test_no_content_type_for_disallowed(self):
        extra = set(constants.EXTENSION_CONTENT_TYPES) - constants.ALLOWED_EXTENSIONS
        assert extra == set(), f"content types for disallowed exts: {extra}"


class TestMediaTypeFilters:
    def test_known_keys(self):
        assert set(constants.MEDIA_TYPE_FILTERS.keys()) == {"audio", "video", "all"}

    def test_filters_are_callable(self):
        for fn in constants.MEDIA_TYPE_FILTERS.values():
            assert callable(fn)
