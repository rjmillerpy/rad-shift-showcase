"""Tests for app/trends/fetchers/google.py — RSS parse of Google daily trends."""

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

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <item>
      <title>foo bar</title>
      <ht:approx_traffic>200+</ht:approx_traffic>
    </item>
    <item>
      <title>baz qux</title>
      <ht:approx_traffic>5000+</ht:approx_traffic>
    </item>
    <item>
      <title></title>
    </item>
  </channel>
</rss>
"""


@pytest.fixture()
def mock_get():
    """Patch the httpx client in `_common` (which is what every fetcher uses now)."""
    with patch("app.trends.fetchers._common.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        yield mock_client


class TestFetchGoogleTrends:
    def test_parses_rss_items(self, mock_get):
        from app.trends.fetchers.google import fetch_google_trends
        from app.trends.schema import SOURCE_GOOGLE

        mock_get.get.return_value = MagicMock(text=_SAMPLE_RSS, raise_for_status=lambda: None)

        items = fetch_google_trends()

        assert len(items) == 2  # empty title skipped
        assert items[0].source == SOURCE_GOOGLE
        assert items[0].keyword == "foo bar"
        assert items[0].volume == "200+"
        assert items[1].rank == 2

    def test_invalid_xml_raises_connection_error(self, mock_get):
        from app.trends.fetchers.google import fetch_google_trends

        mock_get.get.return_value = MagicMock(text="<<not-xml>>", raise_for_status=lambda: None)
        with pytest.raises(ConnectionError, match="invalid XML"):
            fetch_google_trends()

    @pytest.mark.parametrize("payload", [_XML_BOMB, _XML_EXTERNAL_ENTITY], ids=["bomb", "xxe"])
    def test_hostile_xml_is_rejected(self, mock_get, payload):
        from app.trends.fetchers.google import fetch_google_trends

        mock_get.get.return_value = MagicMock(text=payload, raise_for_status=lambda: None)
        with pytest.raises(ConnectionError, match="invalid XML"):
            fetch_google_trends()

    def test_geo_param_templated(self, mock_get):
        from app.trends.fetchers.google import fetch_google_trends

        mock_get.get.return_value = MagicMock(
            text="<rss><channel></channel></rss>", raise_for_status=lambda: None
        )
        fetch_google_trends(geo="JP")
        assert "geo=JP" in mock_get.get.call_args.args[0]

    @pytest.mark.parametrize(
        "exc,match",
        [
            (httpx.TimeoutException("t/o"), "timed out"),
            (
                httpx.HTTPStatusError(
                    "err", request=MagicMock(), response=MagicMock(status_code=503)
                ),
                "HTTP 503",
            ),
            (httpx.ConnectError("dns"), "fetch failed"),
        ],
        ids=["timeout", "http_error", "connect_error"],
    )
    def test_network_errors_become_connection_error(self, mock_get, exc, match):
        from app.trends.fetchers.google import fetch_google_trends

        mock_get.get.side_effect = exc
        with pytest.raises(ConnectionError, match=match):
            fetch_google_trends()

    def test_caps_items_at_max_items(self, mock_get):
        from app.trends.fetchers.google import MAX_ITEMS, fetch_google_trends

        huge_rss = (
            '<?xml version="1.0"?><rss><channel>'
            + "".join(f"<item><title>kw{i}</title></item>" for i in range(MAX_ITEMS + 20))
            + "</channel></rss>"
        )
        mock_get.get.return_value = MagicMock(text=huge_rss, raise_for_status=lambda: None)
        items = fetch_google_trends()
        assert len(items) == MAX_ITEMS
