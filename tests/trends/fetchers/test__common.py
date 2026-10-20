"""Tests for app/trends/fetchers/_common.py — shared HTTP helper."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.trends.fetchers._common import (
    MAX_TITLE_CHARS,
    REQUEST_TIMEOUT_SECONDS,
    http_get_text,
)


@pytest.fixture()
def mock_client():
    with patch("app.trends.fetchers._common.httpx.Client") as mock_cls:
        client = MagicMock()
        mock_cls.return_value.__enter__.return_value = client
        yield client


class TestConstants:
    def test_timeout_bounded(self):
        assert 1 <= REQUEST_TIMEOUT_SECONDS <= 60

    def test_max_title_chars_positive(self):
        assert MAX_TITLE_CHARS > 0


class TestHttpGetText:
    def test_returns_response_text(self, mock_client):
        mock_client.get.return_value = MagicMock(
            text="hello body",
            raise_for_status=lambda: None,
        )
        assert http_get_text("https://example.com", "test") == "hello body"

    def test_forwards_headers(self, mock_client):
        mock_client.get.return_value = MagicMock(text="", raise_for_status=lambda: None)
        headers = {"User-Agent": "audit-bot"}
        http_get_text("https://example.com", "test", headers=headers)
        assert mock_client.get.call_args.kwargs["headers"] == headers

    @pytest.mark.parametrize(
        "exc,match",
        [
            (httpx.TimeoutException("t/o"), "timed out"),
            (
                httpx.HTTPStatusError(
                    "boom",
                    request=MagicMock(),
                    response=MagicMock(status_code=503),
                ),
                "HTTP 503",
            ),
            (httpx.ConnectError("dns"), "fetch failed"),
        ],
        ids=["timeout", "http_error", "connect_error"],
    )
    def test_httpx_errors_wrapped_as_connection_error(self, mock_client, exc, match):
        mock_client.get.side_effect = exc
        with pytest.raises(ConnectionError, match=match):
            http_get_text("https://example.com", "test")

    def test_prefix_is_included_in_error(self, mock_client):
        mock_client.get.side_effect = httpx.TimeoutException("x")
        with pytest.raises(ConnectionError, match="mysource"):
            http_get_text("https://example.com", "mysource")
