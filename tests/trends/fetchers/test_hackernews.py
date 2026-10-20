"""Tests for app/trends/fetchers/hackernews.py — Algolia HN front-page fetch."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

_SAMPLE_HITS = {
    "hits": [
        {"title": "Second by points", "points": 50, "url": "https://a.example", "objectID": "111"},
        {"title": "Top by points", "points": 500, "url": "https://b.example", "objectID": "222"},
        {"title": "", "points": 10, "url": None, "objectID": "333"},
        {"title": "No url item", "points": 30, "url": None, "objectID": "444"},
    ]
}


@pytest.fixture()
def mock_get():
    """Patch the httpx client in `_common` (which is what every fetcher uses now)."""
    with patch("app.trends.fetchers._common.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        yield mock_client


def _text_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.raise_for_status = lambda: None
    return response


class TestFetchHnTop:
    def test_sorts_by_points_desc(self, mock_get):
        from app.trends.fetchers.hackernews import fetch_hn_top

        mock_get.get.return_value = _text_response(json.dumps(_SAMPLE_HITS))
        items = fetch_hn_top()

        assert items[0].keyword == "Top by points"
        assert items[1].keyword == "Second by points"

    def test_falls_back_to_hn_permalink_when_url_missing(self, mock_get):
        from app.trends.fetchers.hackernews import fetch_hn_top

        mock_get.get.return_value = _text_response(json.dumps(_SAMPLE_HITS))
        items = fetch_hn_top()

        no_url_item = next(i for i in items if i.keyword == "No url item")
        assert no_url_item.url is not None
        assert "item?id=444" in no_url_item.url

    def test_skips_empty_titles(self, mock_get):
        from app.trends.fetchers.hackernews import fetch_hn_top

        mock_get.get.return_value = _text_response(json.dumps(_SAMPLE_HITS))
        items = fetch_hn_top()
        assert all(i.keyword for i in items)
        assert len(items) == 3

    @pytest.mark.parametrize(
        "exc,match",
        [
            (httpx.TimeoutException("t/o"), "timed out"),
            (
                httpx.HTTPStatusError(
                    "err", request=MagicMock(), response=MagicMock(status_code=429)
                ),
                "HTTP 429",
            ),
            (httpx.ConnectError("dns"), "fetch failed"),
        ],
        ids=["timeout", "http_error", "connect_error"],
    )
    def test_network_errors_become_connection_error(self, mock_get, exc, match):
        from app.trends.fetchers.hackernews import fetch_hn_top

        mock_get.get.side_effect = exc
        with pytest.raises(ConnectionError, match=match):
            fetch_hn_top()

    def test_invalid_json_becomes_connection_error(self, mock_get):
        from app.trends.fetchers.hackernews import fetch_hn_top

        mock_get.get.return_value = _text_response("<<not json>>")
        with pytest.raises(ConnectionError, match="invalid JSON"):
            fetch_hn_top()
