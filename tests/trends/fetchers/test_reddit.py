"""Tests for app/trends/fetchers/reddit.py — Atom parse of r/popular.

Reddit's public JSON endpoint now returns HTTP 403 for unauthenticated
clients, so the fetcher parses the Atom `.rss` feed from old.reddit.com
instead. Tests exercise the XML parser and the httpx error mapping.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

# Hostile feeds: an entity-expansion bomb ("billion laughs") and an external
# entity that tries to read a local file. Both must be rejected as invalid XML
# rather than expanded or resolved.
_XML_BOMB = (
    '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa">'
    '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
    "<rss><channel><item><title>&c;</title></item></channel></rss>"
)
_XML_EXTERNAL_ENTITY = (
    '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    "<rss><channel><item><title>&x;</title></item></channel></rss>"
)

_SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>First post</title>
    <link href="https://old.reddit.com/r/foo/1"/>
    <category label="r/foo"/>
    <id>t3_a</id>
  </entry>
  <entry>
    <title>Second post</title>
    <link href="https://old.reddit.com/r/bar/2"/>
    <category label="r/bar"/>
    <id>t3_b</id>
  </entry>
  <entry>
    <title></title>
    <link href="https://old.reddit.com/r/baz/3"/>
    <id>t3_c</id>
  </entry>
</feed>
"""


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


class TestFetchRedditPopular:
    def test_parses_atom_entries(self, mock_get):
        from app.trends.fetchers.reddit import fetch_reddit_popular
        from app.trends.schema import SOURCE_REDDIT

        mock_get.get.return_value = _text_response(_SAMPLE_ATOM)

        items = fetch_reddit_popular()

        assert len(items) == 2  # empty-title entry skipped
        assert items[0].source == SOURCE_REDDIT
        assert items[0].keyword == "First post"
        assert items[0].url == "https://old.reddit.com/r/foo/1"
        assert items[0].category == "r/foo"
        # RSS does not carry upvote counts — volume must be None (see reddit.py docstring).
        assert items[0].volume is None
        assert items[1].rank == 2

    def test_invalid_xml_raises_connection_error(self, mock_get):
        from app.trends.fetchers.reddit import fetch_reddit_popular

        mock_get.get.return_value = _text_response("<<not xml>>")
        with pytest.raises(ConnectionError, match="invalid XML"):
            fetch_reddit_popular()

    @pytest.mark.parametrize("payload", [_XML_BOMB, _XML_EXTERNAL_ENTITY], ids=["bomb", "xxe"])
    def test_hostile_xml_is_rejected(self, mock_get, payload):
        from app.trends.fetchers.reddit import fetch_reddit_popular

        mock_get.get.return_value = _text_response(payload)
        with pytest.raises(ConnectionError, match="invalid XML"):
            fetch_reddit_popular()

    def test_http_error_becomes_connection_error(self, mock_get):
        from app.trends.fetchers.reddit import fetch_reddit_popular

        mock_get.get.side_effect = httpx.HTTPStatusError(
            "oops",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )
        with pytest.raises(ConnectionError, match="429"):
            fetch_reddit_popular()
