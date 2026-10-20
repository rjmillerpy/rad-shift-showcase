"""Tests for app/generators/platforms/rss.py — the public RSS adapter."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.generators.platforms.base import PlatformConfigError
from app.generators.platforms.rss import RssAdapter, build_item

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>One</title><description>&lt;p&gt;first&lt;/p&gt;</description><link>https://e.com/1</link></item>
<item><title>Two</title><link>https://e.com/2</link></item>
<item><title>Three</title><description>third</description></item>
</channel></rss>"""


class TestValidateConfig:
    @pytest.mark.parametrize(
        "config",
        [{}, {"feed_url": 5}, {"feed_url": "ftp://e.com/feed"}, {"feed_url": "e.com/feed"}],
        ids=["missing", "not-a-string", "ftp", "no-scheme"],
    )
    def test_rejects_anything_but_an_http_url(self, config):
        with pytest.raises(PlatformConfigError):
            RssAdapter().validate_config(config)

    def test_accepts_https(self):
        RssAdapter().validate_config({"feed_url": "https://e.com/feed.xml"})


class TestFetchItems:
    def _fetch(self, max_items):
        response = MagicMock(content=FEED, headers={})
        with patch("app.generators.platforms.feeds.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = response
            return RssAdapter().fetch_items({"feed_url": "https://e.com/feed.xml"}, max_items)

    def test_turns_entries_into_items_with_html_stripped(self):
        items = self._fetch(10)
        assert [(item.title, item.text, item.link) for item in items] == [
            ("One", "first", "https://e.com/1"),
            ("Two", "Two", "https://e.com/2"),
            ("Three", "third", None),
        ]

    def test_respects_max_items(self):
        assert len(self._fetch(2)) == 2


class TestBuildItem:
    def test_skips_entries_with_no_text_or_title(self):
        assert build_item(SimpleNamespace(get=lambda key, default=None: None)) is None
