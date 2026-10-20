"""API-level tests for app/posts/views/chronicle.py.

The Anthropic SDK is the only thing mocked (an external, paid network
boundary); with it unavailable the service uses its rule-based fallback.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.chronicle.constants import CHRONICLE_MAX_POSTS_PER_PAGE
from app.common.auth_jwt import AuthJWT


@pytest.fixture()
def anthropic_unavailable():
    with patch("app.chronicle.client.anthropic.Anthropic") as sdk:
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("api down")
        stream = MagicMock()
        stream.__enter__ = MagicMock(return_value=MagicMock(text_stream=iter([])))
        stream.__exit__ = MagicMock(return_value=False)
        client.messages.stream.return_value = stream
        sdk.return_value = client
        yield


def _events(body: bytes) -> list[dict]:
    """Decode SSE frames (`data: {json}` lines) into a list of events."""
    prefix = "data: "
    return [
        json.loads(line[len(prefix) :])
        for line in body.decode().splitlines()
        if line.startswith(prefix)
    ]


class TestGetChronicle:
    def test_empty_feed_returns_the_full_envelope(self, client, anthropic_unavailable):
        resp = client.get("/posts/chronicle")

        assert resp.status_code == 200
        assert set(resp.json()) == {"posts", "segments", "page", "has_more", "cached"}
        assert resp.json()["posts"] == []

    def test_segments_only_carry_the_fields_their_type_uses(
        self, client, create_user, create_post, anthropic_unavailable
    ):
        """Regression for the response schema: optional segment fields that
        were absent before must stay absent, not appear as null."""
        create_post(user=create_user(username="writer"), text="A post about coffee #coffee")

        segments = client.get("/posts/chronicle").json()["segments"]

        assert segments
        for segment in segments:
            assert "type" in segment
            assert None not in segment.values()

    def test_posts_use_the_standard_post_shape(
        self, client, create_user, create_post, anthropic_unavailable
    ):
        create_post(user=create_user(username="writer"), text="hello")

        post = client.get("/posts/chronicle").json()["posts"][0]

        assert {"id", "text", "username", "likes", "unix_timestamp"} <= set(post)

    @pytest.mark.parametrize(
        "query",
        [f"posts_per_page={CHRONICLE_MAX_POSTS_PER_PAGE + 1}", "posts_per_page=0", "page=-1"],
        ids=["too-many-per-page", "zero-per-page", "negative-page"],
    )
    def test_out_of_range_paging_is_rejected(self, client, query):
        assert client.get(f"/posts/chronicle?{query}").status_code == 422


class TestChronicleStream:
    def test_is_a_non_buffered_event_stream(self, client, anthropic_unavailable):
        resp = client.get("/posts/chronicle/stream")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"
        assert resp.headers["x-accel-buffering"] == "no"

    def test_starts_with_init_and_ends_with_done(self, client, anthropic_unavailable):
        types = [event["type"] for event in _events(client.get("/posts/chronicle/stream").content)]

        assert types[0] == "init"
        assert types[-1] == "done"

    @pytest.mark.parametrize(
        "token",
        ["", "not.a.token", "garbage"],
        ids=["empty", "malformed", "not-a-jwt"],
    )
    def test_a_bad_query_token_falls_back_to_anonymous(self, client, token, anthropic_unavailable):
        """SSE can't send headers, so the JWT arrives as ?token=. A bad one
        must not break the public stream."""
        assert client.get(f"/posts/chronicle/stream?token={token}").status_code == 200

    def test_token_for_a_deleted_user_falls_back_to_anonymous(self, client, anthropic_unavailable):
        token = AuthJWT().create_access_token(subject="ghost")
        assert client.get(f"/posts/chronicle/stream?token={token}").status_code == 200

    def test_a_valid_token_personalises_the_stream(
        self, client, create_user, create_post, auth_header, anthropic_unavailable
    ):
        create_post(user=create_user(username="writer"), text="mine")
        token = auth_header("writer")["Authorization"].split(" ")[1]

        init = _events(client.get(f"/posts/chronicle/stream?token={token}").content)[0]
        anonymous = _events(client.get("/posts/chronicle/stream").content)[0]

        assert init["posts"][0]["is_me"] is True
        assert anonymous["posts"][0]["is_me"] is False

    @pytest.mark.parametrize(
        "query",
        [f"posts_per_page={CHRONICLE_MAX_POSTS_PER_PAGE + 1}", "page=-1"],
        ids=["too-many-per-page", "negative-page"],
    )
    def test_out_of_range_paging_is_rejected(self, client, query):
        assert client.get(f"/posts/chronicle/stream?{query}").status_code == 422
