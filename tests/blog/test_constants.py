"""Tests for app/blog/constants.py — enum values and numeric invariants."""

from app.blog import constants


class TestAdPlacementEnum:
    def test_values(self):
        assert {a.value for a in constants.AdPlacement} == {"none", "minimal", "standard"}

    def test_string_enum_compares_to_raw_value(self):
        assert constants.AdPlacement.NONE == "none"
        assert constants.AdPlacement.MINIMAL == "minimal"


class TestNumericConstants:
    def test_title_len_positive(self):
        assert constants.MAX_TITLE_LEN > 0

    def test_seo_desc_ellipsis_within_max(self):
        assert (
            constants.SEO_DESC_TRUNCATE_AT + len(constants.SEO_DESC_ELLIPSIS)
            == constants.SEO_DESC_MAX_LEN
        )

    def test_words_per_minute_reasonable(self):
        assert 100 <= constants.WORDS_PER_MINUTE <= 400

    def test_list_limits(self):
        assert constants.DEFAULT_LIST_LIMIT <= constants.MAX_LIST_LIMIT

    def test_read_time_cap_bounded_but_generous(self):
        assert 0 < constants.MAX_READ_TIME_SECONDS <= 24 * 60 * 60
