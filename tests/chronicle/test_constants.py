"""Tests for app/chronicle/constants.py — invariants on tunables."""

from app.chronicle import constants


class TestNumericTunables:
    def test_model_is_haiku(self):
        assert "haiku" in constants.CHRONICLE_MODEL.lower()

    def test_max_tokens_positive(self):
        assert constants.CHRONICLE_MAX_TOKENS > 0

    def test_cache_ttl_positive(self):
        assert constants.CHRONICLE_CACHE_SECONDS > 0

    def test_context_chars_positive(self):
        assert constants.CHRONICLE_CONTEXT_CHARS > 0

    def test_batch_size_positive(self):
        assert constants.CHRONICLE_BATCH_SIZE > 0

    def test_anthropic_timeout_bounded(self):
        assert 1 <= constants.ANTHROPIC_TIMEOUT_SECONDS <= 120


class TestSimilarityWeights:
    def test_same_author_dominant(self):
        # Two posts by the same author should count for more than a single tag match.
        assert constants.SAME_AUTHOR_WEIGHT > constants.TAG_OVERLAP_WEIGHT

    def test_word_overlap_capped(self):
        assert constants.WORD_OVERLAP_CAP > 0
        assert constants.WORD_OVERLAP_WEIGHT > 0

    def test_min_word_len_filters_stopwords(self):
        assert constants.MIN_WORD_LEN_FOR_MATCH >= 3


class TestFallbackText:
    def test_pools_non_empty(self):
        assert constants.MISSING_INDEX_FILLERS
        assert constants.FALLBACK_INTROS
        assert constants.FALLBACK_TRANSITIONS

    def test_intros_have_username_placeholder(self):
        for line in constants.FALLBACK_INTROS:
            assert "{u}" in line

    def test_opening_and_closing_non_empty(self):
        assert constants.FALLBACK_OPENING.strip()
        assert constants.FALLBACK_CLOSING.strip()
