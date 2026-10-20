"""Tests for app/chronicle/parsing.py — segment parser + rule-based fallback."""

import pytest

from app.chronicle import parsing
from app.chronicle.constants import (
    FALLBACK_CLOSING,
    FALLBACK_OPENING,
)
from tests.chronicle.helpers import make_post as _post


class TestParseChronicleSegments:
    def test_valid_json_array(self):
        raw = '[{"type":"narrative","text":"Hi. "},{"type":"post","index":0}]'
        result = parsing.parse_chronicle_segments(raw, post_count=1)
        assert result == [
            {"type": "narrative", "text": "Hi. "},
            {"type": "post", "index": 0},
        ]

    def test_strips_code_fences(self):
        raw = '```json\n[{"type":"post","index":0}]\n```'
        result = parsing.parse_chronicle_segments(raw, post_count=1)
        assert result == [{"type": "post", "index": 0}]

    def test_extracts_array_from_surrounding_text(self):
        raw = 'sure, here you go: [{"type":"post","index":0}] hope that works!'
        result = parsing.parse_chronicle_segments(raw, post_count=1)
        assert result == [{"type": "post", "index": 0}]

    def test_none_on_no_brackets(self):
        assert parsing.parse_chronicle_segments("no brackets here", post_count=1) is None

    def test_none_on_non_list_root(self):
        assert parsing.parse_chronicle_segments('{"type":"post","index":0}', 1) is None

    def test_out_of_range_index_dropped_but_filler_added(self):
        raw = '[{"type":"post","index":5}]'
        result = parsing.parse_chronicle_segments(raw, post_count=1)
        # The 5 is out of range, so it's dropped; the missing index 0 gets a filler + post.
        assert result is not None
        indices = [s["index"] for s in result if s["type"] == "post"]
        assert indices == [0]

    def test_duplicate_index_deduped(self):
        raw = (
            '[{"type":"post","index":0},'
            '{"type":"narrative","text":"middle. "},'
            '{"type":"post","index":0}]'
        )
        result = parsing.parse_chronicle_segments(raw, post_count=1)
        post_segs = [s for s in result if s["type"] == "post"]
        assert len(post_segs) == 1

    def test_em_dash_replaced(self):
        raw = '[{"type":"narrative","text":"before — after"}]'
        result = parsing.parse_chronicle_segments(raw, post_count=0)
        assert "—" not in result[0]["text"]
        assert "," in result[0]["text"]

    def test_missing_indices_get_filler(self):
        # Two posts declared but only index 0 in the LLM output.
        raw = '[{"type":"post","index":0}]'
        result = parsing.parse_chronicle_segments(raw, post_count=3)
        indices = [s["index"] for s in result if s["type"] == "post"]
        assert sorted(indices) == [0, 1, 2]

    @pytest.mark.parametrize(
        "raw",
        ['{"not": "an array"}', '["string not dict"]', "[]", '[{"missing": "type"}]'],
        ids=["obj_root", "string_element", "empty_array", "no_type"],
    )
    def test_returns_none_when_nothing_usable(self, raw):
        result = parsing.parse_chronicle_segments(raw, post_count=0)
        assert result is None or result == []


class TestBuildFallbackSegments:
    def test_opening_and_closing_present(self):
        posts = [_post(id=1, username="alice", text="hi")]
        segments = parsing.build_fallback_segments(posts)
        assert segments[0]["text"] == FALLBACK_OPENING
        assert segments[-1]["text"] == FALLBACK_CLOSING

    def test_every_post_included(self):
        posts = [_post(id=i, username=f"u{i}") for i in range(3)]
        segments = parsing.build_fallback_segments(posts)
        indices = [s["index"] for s in segments if s["type"] in ("post", "media")]
        assert indices == [0, 1, 2]

    def test_media_type_used_when_media_present(self):
        posts = [_post(id=1, image_url="https://example.com/a.png")]
        segments = parsing.build_fallback_segments(posts)
        media_segs = [s for s in segments if s["type"] == "media"]
        assert len(media_segs) == 1

    def test_no_media_kind_for_text_only_post(self):
        posts = [_post(id=1)]
        segments = parsing.build_fallback_segments(posts)
        media_segs = [s for s in segments if s["type"] == "media"]
        assert media_segs == []
