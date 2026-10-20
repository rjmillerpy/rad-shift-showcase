"""Tests for app/posts/schema.py — PostCreateRequest + SlopRequest + PostResponse."""

import pytest
from pydantic import ValidationError

from app.posts.constants import MAX_POST_TEXT_CHARS
from app.posts.schema import PostCreateRequest, PostResponse, SlopRequest


class TestPostCreateRequest:
    def test_minimal_valid(self):
        req = PostCreateRequest(text="Hello")
        assert req.text == "Hello"
        assert req.post_metadata == "{}"
        assert req.is_draft is False
        assert req.parent_post_id is None
        assert req.is_reply is False

    def test_max_length_text_accepted(self):
        req = PostCreateRequest(text="A" * MAX_POST_TEXT_CHARS)
        assert len(req.text) == MAX_POST_TEXT_CHARS

    def test_text_exceeds_max_length(self):
        with pytest.raises(ValidationError):
            PostCreateRequest(text="A" * (MAX_POST_TEXT_CHARS + 1))

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            PostCreateRequest()

    @pytest.mark.parametrize(
        "text_len",
        [1, 100, 2500, MAX_POST_TEXT_CHARS - 1, MAX_POST_TEXT_CHARS],
        ids=["1", "100", "2500", "cap_minus_1", "at_cap"],
    )
    def test_various_text_lengths(self, text_len):
        req = PostCreateRequest(text="x" * text_len)
        assert len(req.text) == text_len

    @pytest.mark.parametrize("is_draft", [True, False], ids=["draft", "published"])
    def test_draft_flag(self, is_draft):
        req = PostCreateRequest(text="test", is_draft=is_draft)
        assert req.is_draft is is_draft

    def test_with_parent_post_id(self):
        req = PostCreateRequest(text="reply", parent_post_id=42, is_reply=True)
        assert req.parent_post_id == 42
        assert req.is_reply is True


class TestSlopRequest:
    def test_valid_reason(self):
        assert SlopRequest(reason="spam").reason == "spam"

    def test_reason_required(self):
        with pytest.raises(ValidationError):
            SlopRequest()

    def test_empty_reason_rejected(self):
        with pytest.raises(ValidationError):
            SlopRequest(reason="")

    @pytest.mark.parametrize(
        "reason",
        ["a", "spam content", "A" * 500],
        ids=["single_char", "phrase", "500_chars"],
    )
    def test_various_reasons(self, reason):
        assert SlopRequest(reason=reason).reason == reason


class TestPostResponse:
    """PostResponse is a dataclass (not Pydantic) — construct + inspect."""

    def _minimal_kwargs(self, **overrides) -> dict:
        base = {
            "id": 1,
            "text": "hi",
            "likes": 0,
            "shares": 0,
            "reposts": 0,
            "saves": 0,
            "laughs": 0,
            "liked_by_me": False,
            "unix_timestamp": 1_700_000_000,
            "post_metadata": {},
            "username": "alice",
            "profile_picture_url": None,
            "image_url": None,
            "video_url": None,
            "audio_url": None,
        }
        base.update(overrides)
        return base

    def test_minimal_construction(self):
        resp = PostResponse(**self._minimal_kwargs())
        assert resp.id == 1
        assert resp.username == "alice"

    def test_defaults(self):
        resp = PostResponse(**self._minimal_kwargs())
        assert resp.image_urls is None
        assert resp.replies_count == 0
        assert resp.quoted_post is None

    def test_asdict_roundtrip(self):
        from dataclasses import asdict

        payload = asdict(PostResponse(**self._minimal_kwargs()))
        assert payload["id"] == 1
        assert "likes" in payload
