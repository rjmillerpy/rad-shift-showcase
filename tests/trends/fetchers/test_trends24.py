"""Tests for app/trends/fetchers/trends24.py — HTML scrape of trends24.in."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

_SAMPLE_HTML = """
<html><body>
<ol class="trend-card__list">
  <li><a class="trend-link" href="https://twitter.com/search?q=alpha">#Alpha</a></li>
  <li><a class="trend-link" href="https://twitter.com/search?q=bravo">Bravo</a></li>
  <li><a class="trend-link" href="https://twitter.com/search?q=alpha">#Alpha</a></li>
  <li><a class="trend-link" href="https://twitter.com/search?q=charlie"></a></li>
</ol>
</body></html>
"""


@pytest.fixture()
def mock_get():
    """Patch the httpx client in `_common` (which is what every fetcher uses now)."""
    with patch("app.trends.fetchers._common.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        yield mock_client


class TestFetchTrends24:
    def test_returns_trend_items(self, mock_get):
        from app.trends.fetchers.trends24 import fetch_trends24
        from app.trends.schema import SOURCE_TRENDS24

        mock_get.get.return_value = MagicMock(text=_SAMPLE_HTML, raise_for_status=lambda: None)

        items = fetch_trends24()

        assert len(items) == 2
        assert items[0].source == SOURCE_TRENDS24
        assert items[0].rank == 1
        assert items[0].keyword == "#Alpha"
        assert items[1].rank == 2
        assert items[1].keyword == "Bravo"

    def test_dedupes_repeated_keywords(self, mock_get):
        """Same trend appearing in multiple hourly buckets must not be duplicated."""
        from app.trends.fetchers.trends24 import fetch_trends24

        mock_get.get.return_value = MagicMock(text=_SAMPLE_HTML, raise_for_status=lambda: None)
        items = fetch_trends24()
        keywords = [i.keyword for i in items]
        assert keywords.count("#Alpha") == 1

    def test_region_url_is_templated(self, mock_get):
        from app.trends.fetchers.trends24 import fetch_trends24

        mock_get.get.return_value = MagicMock(text="<html></html>", raise_for_status=lambda: None)
        fetch_trends24(region="japan")

        call_args = mock_get.get.call_args
        assert "japan" in call_args.args[0]

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
    def test_network_errors_become_connection_error(self, mock_get, exc, match):
        from app.trends.fetchers.trends24 import fetch_trends24

        mock_get.get.side_effect = exc
        with pytest.raises(ConnectionError, match=match):
            fetch_trends24()
