"""Tests for app/chronicle/client.py — Anthropic wrapper.

External-boundary (network) is patched. Only the wrapper's own behavior is
under test: key detection, singleton reuse, graceful failure paths.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.chronicle import client


@pytest.fixture(autouse=True)
def _reset_between_tests(monkeypatch):
    client.reset_client()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield
    client.reset_client()


class TestGetClient:
    def test_returns_none_when_key_missing(self):
        assert client.get_client() is None

    def test_returns_shared_instance_when_key_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("app.chronicle.client.anthropic.Anthropic") as ctor:
            ctor.return_value = MagicMock(name="anthropic_client")
            first = client.get_client()
            second = client.get_client()
        assert first is second
        assert ctor.call_count == 1


class TestCallHaiku:
    def test_returns_none_when_key_missing(self):
        assert client.call_haiku("prompt", "sys") is None

    def test_returns_none_when_sdk_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("app.chronicle.client.anthropic.Anthropic") as ctor:
            fake = MagicMock()
            fake.messages.create.side_effect = RuntimeError("api down")
            ctor.return_value = fake
            assert client.call_haiku("prompt", "sys") is None

    def test_returns_response_text_on_success(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("app.chronicle.client.anthropic.Anthropic") as ctor:
            fake = MagicMock()
            response = MagicMock()
            response.content = [MagicMock(type="text", text="hello world")]
            fake.messages.create.return_value = response
            ctor.return_value = fake
            assert client.call_haiku("prompt", "sys") == "hello world"
            assert fake.messages.create.call_args.kwargs["system"] == "sys"

    def test_skips_leading_non_text_blocks(self, monkeypatch):
        """A response can open with e.g. a thinking block; use the first text block."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("app.chronicle.client.anthropic.Anthropic") as ctor:
            fake = MagicMock()
            response = MagicMock()
            response.content = [
                MagicMock(type="thinking", spec=["type", "thinking"]),
                MagicMock(type="text", text="the story"),
            ]
            fake.messages.create.return_value = response
            ctor.return_value = fake
            assert client.call_haiku("prompt", "sys") == "the story"

    def test_returns_none_when_response_content_empty(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("app.chronicle.client.anthropic.Anthropic") as ctor:
            fake = MagicMock()
            response = MagicMock()
            response.content = []
            fake.messages.create.return_value = response
            ctor.return_value = fake
            assert client.call_haiku("prompt", "sys") is None


class TestStreamHaiku:
    def test_yields_nothing_when_key_missing(self):
        tokens = list(client.stream_haiku("prompt", "sys"))
        assert tokens == []

    def test_yields_nothing_when_sdk_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("app.chronicle.client.anthropic.Anthropic") as ctor:
            fake = MagicMock()
            fake.messages.stream.side_effect = RuntimeError("boom")
            ctor.return_value = fake
            assert list(client.stream_haiku("prompt", "sys")) == []

    def test_yields_tokens_from_text_stream(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("app.chronicle.client.anthropic.Anthropic") as ctor:
            fake = MagicMock()
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=MagicMock(text_stream=iter(["a", "b"])))
            ctx.__exit__ = MagicMock(return_value=False)
            fake.messages.stream.return_value = ctx
            ctor.return_value = fake
            assert list(client.stream_haiku("prompt", "sys")) == ["a", "b"]
