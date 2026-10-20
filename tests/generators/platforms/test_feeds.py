"""app/generators/platforms/feeds.py: the shared RSS download and entry parsing.

httpx.Client is the external boundary and is replaced with a fake client.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.generators.items import ScrapedItem
from app.generators.platforms.feeds import (
    MAX_FEED_RESPONSE_BYTES,
    USER_AGENT,
    fetch_feed,
    parse_entries,
    strip_html,
)

URL = "https://feeds.example/rss"


def _client_returning(response=None, error=None):
    client = MagicMock()
    client.__enter__.return_value = client
    if error is not None:
        client.get.side_effect = error
    else:
        client.get.return_value = response
    return client


def _response(content=b"<rss/>", headers=None, status_error=None):
    response = MagicMock(content=content, headers=headers or {})
    response.raise_for_status.side_effect = status_error
    return response


class TestFetchFeed:
    @patch("app.generators.platforms.feeds.httpx.Client")
    def test_returns_the_body_and_identifies_itself(self, client_cls):
        client = _client_returning(_response(b"<rss>ok</rss>"))
        client_cls.return_value = client
        assert fetch_feed(URL, source="Pinterest") == b"<rss>ok</rss>"
        assert client.get.call_args.kwargs["headers"] == {"User-Agent": USER_AGENT}

    @patch("app.generators.platforms.feeds.httpx.Client")
    def test_refuses_an_oversized_feed(self, client_cls):
        too_big = {"content-length": str(MAX_FEED_RESPONSE_BYTES + 1)}
        client_cls.return_value = _client_returning(_response(headers=too_big))
        with pytest.raises(ValueError, match="Feed too large"):
            fetch_feed(URL, source="Pinterest")

    @patch("app.generators.platforms.feeds.httpx.Client")
    def test_a_timeout_names_the_source(self, client_cls):
        client_cls.return_value = _client_returning(error=httpx.TimeoutException("slow"))
        with pytest.raises(ConnectionError, match=f"Timeout fetching Example feed {URL}"):
            fetch_feed(URL, source="Example")

    @patch("app.generators.platforms.feeds.httpx.Client")
    def test_an_http_error_names_the_status_and_source(self, client_cls):
        error = httpx.HTTPStatusError(
            "nope", request=MagicMock(), response=MagicMock(status_code=503)
        )
        client_cls.return_value = _client_returning(_response(status_error=error))
        with pytest.raises(ConnectionError, match="HTTP 503 from Pinterest feed"):
            fetch_feed(URL, source="Pinterest")


class TestParseEntries:
    def test_caps_and_skips_rejected_entries(self):
        def build(entry):
            return (
                None
                if entry == "skip"
                else ScrapedItem(title=entry, text=entry, image_url=None, link=None, popularity=0)
            )

        items = parse_entries(["a", "skip", "b", "c"], max_items=3, build=build)
        assert [i.title for i in items] == ["a", "b"]


@pytest.mark.parametrize(
    "html,text",
    [("<p>Hello <b>world</b></p>", "Hello world"), ("a&nbsp;b", "a b"), ("  plain  ", "plain")],
    ids=["tags", "nbsp", "whitespace"],
)
def test_strip_html(html, text):
    assert strip_html(html) == text
