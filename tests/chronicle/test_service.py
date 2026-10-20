"""API-level + orchestration tests for app/chronicle/service.py.

Direct unit tests for the helpers live in test_parsing.py, test_grouping.py,
test_cache.py, test_prompt.py, and test_client.py.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.chronicle import cache
from app.chronicle import client as chronicle_client
from app.chronicle.constants import CHRONICLE_MAX_POSTS_PER_PAGE, FALLBACK_OPENING
from app.flags.constants import Flag


@pytest.fixture(autouse=True)
def _reset_chronicle_state(monkeypatch):
    """Ensure each test starts with an empty cache and a re-resolvable client."""
    cache.clear()
    chronicle_client.reset_client()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    yield
    cache.clear()
    chronicle_client.reset_client()


def _install_noop_anthropic() -> patch:
    """Patch the Anthropic SDK so `call_haiku` / `stream_haiku` degrade to fallback."""
    cls_patch = patch("app.chronicle.client.anthropic.Anthropic")
    mock_cls = cls_patch.start()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("api down")
    stream_ctx = MagicMock()
    stream_ctx.__enter__ = MagicMock(return_value=MagicMock(text_stream=iter([])))
    stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_client.messages.stream.return_value = stream_ctx
    mock_cls.return_value = mock_client
    return cls_patch


class TestChronicleEndpoint:
    def test_endpoint_returns_segments_and_posts(
        self, client, create_user, create_post, auth_header
    ):
        user = create_user(username="chron_user")
        create_post(user=user, text="A test post for chronicle")
        cls_patch = _install_noop_anthropic()
        try:
            resp = client.get("/posts/chronicle", headers=auth_header("chron_user"))
        finally:
            cls_patch.stop()
        assert resp.status_code == 200
        data = resp.json()
        assert "segments" in data
        assert "posts" in data
        assert data["cached"] is False

    def test_endpoint_empty_feed(self, client):
        resp = client.get("/posts/chronicle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["segments"] == []
        assert data["posts"] == []

    def test_pagination_offset(self, client, create_user, create_post, auth_header):
        user = create_user(username="chron_page")
        for i in range(5):
            create_post(user=user, text=f"Chronicle post {i}")
        cls_patch = _install_noop_anthropic()
        try:
            resp = client.get(
                "/posts/chronicle?page=0&posts_per_page=2",
                headers=auth_header("chron_page"),
            )
        finally:
            cls_patch.stop()
        assert resp.status_code == 200
        assert resp.json()["has_more"] is True


class TestChronicleCache:
    def test_second_call_returns_cached_flag(self, client, create_user, create_post, auth_header):
        user = create_user(username="chron_cache")
        create_post(user=user, text="Cached story")
        cls_patch = _install_noop_anthropic()
        try:
            first = client.get("/posts/chronicle", headers=auth_header("chron_cache")).json()
            second = client.get("/posts/chronicle", headers=auth_header("chron_cache")).json()
        finally:
            cls_patch.stop()
        assert first["cached"] is False
        assert second["cached"] is True
        assert first["segments"] == second["segments"]


def _anthropic_returning(text: str) -> tuple[patch, MagicMock]:
    """Patch the Anthropic SDK to answer `text`; returns the patch and the fake client."""
    cls_patch = patch("app.chronicle.client.anthropic.Anthropic")
    mock_client = MagicMock()
    block = MagicMock(type="text", text=text)
    mock_client.messages.create.return_value = MagicMock(content=[block])
    stream_ctx = MagicMock()
    stream_ctx.__enter__ = MagicMock(return_value=MagicMock(text_stream=iter([text])))
    stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_client.messages.stream.return_value = stream_ctx
    cls_patch.start().return_value = mock_client
    return cls_patch, mock_client


LLM_OUTPUT = '[{"type":"narrative","text":"Told by the model. "},{"type":"post","index":0}]'


def _narratives(segments: list[dict]) -> list[str]:
    return [s["text"] for s in segments if s["type"] == "narrative"]


class TestChronicleWithMockedApi:
    """The paths that used to live in tests/posts/test_api_chronicle.py."""

    @pytest.fixture(autouse=True)
    def _narration_on(self, set_flags):
        set_flags({Flag.CHRONICLE_LLM_NARRATION: True})

    def _install_anthropic_returning(self, text: str) -> patch:
        cls_patch = patch("app.chronicle.client.anthropic.Anthropic")
        mock_cls = cls_patch.start()
        mock_client = MagicMock()
        response = MagicMock()
        block = MagicMock()
        block.type = "text"
        block.text = text
        response.content = [block]
        mock_client.messages.create.return_value = response
        mock_cls.return_value = mock_client
        return cls_patch

    def test_anonymous_call_returns_200(
        self,
        client,
        create_user,
        create_post,
        auth_header,
    ):
        user = create_user(username="chron_anon_author")
        create_post(user=user, text="Public post visible in algo feed")
        cls_patch = _install_noop_anthropic()
        try:
            resp = client.get("/posts/chronicle?page=0")
        finally:
            cls_patch.stop()
        assert resp.status_code == 200

    def test_valid_llm_json_is_parsed_into_segments(
        self,
        client,
        create_user,
        create_post,
        auth_header,
    ):
        user = create_user(username="chron_parse_ok")
        create_post(user=user, text="Parseable post")
        api_output = (
            '[{"type":"narrative","text":"Once. "},'
            '{"type":"post","index":0},'
            '{"type":"narrative","text":"said @chron_parse_ok. End."}]'
        )
        cls_patch = self._install_anthropic_returning(api_output)
        try:
            resp = client.get(
                "/posts/chronicle?page=0&posts_per_page=1",
                headers=auth_header("chron_parse_ok"),
            )
        finally:
            cls_patch.stop()
        segments = resp.json()["segments"]
        assert any(s["type"] == "post" for s in segments)
        assert "Once. " in _narratives(segments), "the model's text, not the rule-based fallback"

    def test_non_json_llm_output_degrades_to_fallback(
        self,
        client,
        create_user,
        create_post,
        auth_header,
    ):
        user = create_user(username="chron_bad_output")
        create_post(user=user, text="Bad output test")
        cls_patch = self._install_anthropic_returning("not json at all")
        try:
            resp = client.get(
                "/posts/chronicle?page=0&posts_per_page=1",
                headers=auth_header("chron_bad_output"),
            )
        finally:
            cls_patch.stop()
        assert resp.status_code == 200
        assert len(resp.json()["segments"]) > 0

    def test_em_dashes_stripped_from_narrative(
        self,
        client,
        create_user,
        create_post,
        auth_header,
    ):
        user = create_user(username="chron_emdash")
        create_post(user=user, text="Dash test")
        api_output = (
            '[{"type":"narrative","text":"Hello — world"},'
            '{"type":"post","index":0},'
            '{"type":"narrative","text":"done"}]'
        )
        cls_patch = self._install_anthropic_returning(api_output)
        try:
            resp = client.get(
                "/posts/chronicle?page=0&posts_per_page=1",
                headers=auth_header("chron_emdash"),
            )
        finally:
            cls_patch.stop()
        narratives = _narratives(resp.json()["segments"])
        assert any(text.startswith("Hello") for text in narratives), "the model's text was used"
        assert not any("—" in text for text in narratives)


class TestChronicleStream:
    def _read_sse(self, body: bytes) -> list[dict]:
        """The endpoint emits SSE frames: `data: {json}\\n\\n` per event."""
        events = []
        for line in body.decode().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
        return events

    def test_stream_emits_init_and_done_when_empty(self, client):
        resp = client.get("/posts/chronicle/stream")
        assert resp.status_code == 200
        events = self._read_sse(resp.content)
        types = [e["type"] for e in events]
        assert types == ["init", "done"]

    def test_stream_emits_init_segments_and_done(
        self,
        client,
        create_user,
        create_post,
        auth_header,
    ):
        user = create_user(username="chron_stream")
        create_post(user=user, text="Stream post")
        headers = auth_header("chron_stream")
        token = headers["Authorization"].split(" ")[1]

        cls_patch = _install_noop_anthropic()
        try:
            resp = client.get(f"/posts/chronicle/stream?token={token}")
        finally:
            cls_patch.stop()

        assert resp.status_code == 200
        events = self._read_sse(resp.content)
        types = [e["type"] for e in events]
        assert types[0] == "init"
        assert types[-1] == "done"
        assert "segment" in types  # fallback path emits per-segment events


class TestChroniclePagingBounds:
    """posts_per_page drives LLM spend on a public endpoint, so it is capped."""

    @pytest.mark.parametrize("path", ["/posts/chronicle", "/posts/chronicle/stream"])
    @pytest.mark.parametrize(
        "query",
        [
            f"posts_per_page={CHRONICLE_MAX_POSTS_PER_PAGE + 1}",
            "posts_per_page=0",
            "page=-1",
        ],
    )
    def test_out_of_range_params_rejected(self, client, path, query):
        resp = client.get(f"{path}?{query}")
        assert resp.status_code == 422


class TestNarrationFlag:
    """chronicle-llm-narration decides per user whether Claude narrates (and is paid for)."""

    def _stream(self, client, headers):
        # Browsers can't set headers on an event stream, so it takes ?token=.
        token = headers["Authorization"].removeprefix("Bearer ")
        return client.get(f"/posts/chronicle/stream?page=0&posts_per_page=1&token={token}")

    def _get(self, client, headers=None):
        return client.get("/posts/chronicle?page=0&posts_per_page=1", headers=headers or {})

    def test_off_makes_no_llm_call_and_narrates_by_rules(
        self, client, create_user, create_post, auth_header, set_flags
    ):
        set_flags({Flag.CHRONICLE_LLM_NARRATION: False})
        create_post(user=create_user(username="flag_off"), text="A post")
        cls_patch, fake = _anthropic_returning(LLM_OUTPUT)
        try:
            resp = self._get(client, auth_header("flag_off"))
        finally:
            cls_patch.stop()
        fake.messages.create.assert_not_called()
        assert _narratives(resp.json()["segments"])[0] == FALLBACK_OPENING

    def test_admins_get_llm_narration_from_the_checked_in_flags(
        self, client, create_user, create_post, auth_header
    ):
        create_post(user=create_user(username="flag_admin", is_admin=True), text="A post")
        cls_patch, fake = _anthropic_returning(LLM_OUTPUT)
        try:
            resp = self._get(client, auth_header("flag_admin"))
        finally:
            cls_patch.stop()
        fake.messages.create.assert_called_once()
        assert "Told by the model. " in _narratives(resp.json()["segments"])

    def test_anonymous_visitors_never_get_llm_narration(self, client, create_user, create_post):
        create_post(user=create_user(username="flag_anon_author"), text="A post")
        cls_patch, fake = _anthropic_returning(LLM_OUTPUT)
        try:
            self._get(client)
        finally:
            cls_patch.stop()
        fake.messages.create.assert_not_called()

    def test_cached_llm_text_is_not_served_once_the_flag_is_off(
        self, client, create_user, create_post, auth_header, set_flags
    ):
        create_post(user=create_user(username="flag_cache"), text="A post")
        cls_patch, _ = _anthropic_returning(LLM_OUTPUT)
        try:
            set_flags({Flag.CHRONICLE_LLM_NARRATION: True})
            first = self._get(client, auth_header("flag_cache")).json()
            set_flags({Flag.CHRONICLE_LLM_NARRATION: False})
            second = self._get(client, auth_header("flag_cache")).json()
        finally:
            cls_patch.stop()
        assert "Told by the model. " in _narratives(first["segments"])
        assert second["cached"] is False
        assert _narratives(second["segments"])[0] == FALLBACK_OPENING

    def test_off_streams_no_tokens(self, client, create_user, create_post, auth_header, set_flags):
        set_flags({Flag.CHRONICLE_LLM_NARRATION: False})
        create_post(user=create_user(username="flag_stream"), text="A post")
        cls_patch, fake = _anthropic_returning(LLM_OUTPUT)
        try:
            resp = self._stream(client, auth_header("flag_stream"))
        finally:
            cls_patch.stop()
        events = [
            json.loads(line.removeprefix("data: ")) for line in resp.text.splitlines() if line
        ]
        fake.messages.stream.assert_not_called()
        assert "token" not in {e["type"] for e in events}
        assert any(e["type"] == "segment" for e in events)

    def test_on_streams_the_models_tokens(
        self, client, create_user, create_post, auth_header, set_flags
    ):
        set_flags({Flag.CHRONICLE_LLM_NARRATION: True})
        create_post(user=create_user(username="flag_stream_on"), text="A post")
        cls_patch, _ = _anthropic_returning(LLM_OUTPUT)
        try:
            resp = self._stream(client, auth_header("flag_stream_on"))
        finally:
            cls_patch.stop()
        events = [
            json.loads(line.removeprefix("data: ")) for line in resp.text.splitlines() if line
        ]
        assert [e["token"] for e in events if e["type"] == "token"] == [LLM_OUTPUT]
