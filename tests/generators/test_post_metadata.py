"""Tests for app/generators/post_metadata.py — link-card metadata builders."""

import pytest

from app.generators.items import ScrapedItem
from app.generators.models import GeneratorSource
from app.generators.post_metadata import (
    build_link_card,
    build_scraped_post_metadata,
    build_source_metadata,
)


def _make_source(**overrides) -> GeneratorSource:
    defaults = {
        "name": "r/python",
        "site_url": "https://reddit.com/r/python",
        "platform": "reddit",
        "platform_config": {"subreddit": "python"},
        "config": {},
    }
    defaults.update(overrides)
    return GeneratorSource(**defaults)


def _make_item(**overrides) -> ScrapedItem:
    defaults = {
        "title": "Hello",
        "text": "Body",
        "image_url": "https://img.example.com/a.jpg",
        "link": "https://example.com/post/1",
        "popularity": 0,
    }
    defaults.update(overrides)
    return ScrapedItem(**defaults)


class TestBuildSourceMetadata:
    @pytest.mark.parametrize(
        "platform,name,expected_label",
        [
            ("reddit", "r/python", "Reddit · r/python"),
            ("pinterest", "nasa pins", "Pinterest · nasa pins"),
            ("web", "Hacker News", "Hacker News"),
            ("web", "", "Web"),
            ("reddit", "", "Reddit"),
            ("unknown_platform", "Foo", "Unknown_Platform · Foo"),
        ],
        ids=["reddit", "pinterest", "web-named", "web-empty", "reddit-empty", "unknown"],
    )
    def test_label_composition(self, platform, name, expected_label):
        source = _make_source(platform=platform, name=name)
        meta = build_source_metadata(source)
        assert meta["label"] == expected_label
        assert meta["platform"] == platform
        assert meta["name"] == name.strip()

    def test_url_is_passed_through(self):
        source = _make_source(site_url="https://reddit.com/r/python")
        meta = build_source_metadata(source)
        assert meta["url"] == "https://reddit.com/r/python"

    def test_blank_url_becomes_none(self):
        source = _make_source(site_url="   ")
        meta = build_source_metadata(source)
        assert meta["url"] is None


class TestBuildLinkCard:
    def test_returns_none_when_item_has_no_link(self):
        item = _make_item(link=None)
        assert build_link_card(item) is None

    def test_full_fields_when_present(self):
        item = _make_item(
            link="https://news.ycombinator.com/item?id=1",
            title="A great post",
            image_url="https://img.example.com/a.jpg",
        )
        card = build_link_card(item)
        assert card == {
            "url": "https://news.ycombinator.com/item?id=1",
            "title": "A great post",
            "image": "https://img.example.com/a.jpg",
            "hostname": "news.ycombinator.com",
            "is_video": False,
        }

    def test_title_and_image_can_be_none(self):
        item = _make_item(title=None, image_url=None)
        card = build_link_card(item)
        assert card is not None
        assert card["title"] is None
        assert card["image"] is None

    @pytest.mark.parametrize(
        "url,expected_host",
        [
            ("https://news.ycombinator.com/item?id=1", "news.ycombinator.com"),
            ("http://example.com/x", "example.com"),
            ("https://www.reddit.com/r/python/", "www.reddit.com"),
            ("not a url", None),
        ],
        ids=["hn", "plain", "reddit", "garbage"],
    )
    def test_hostname_extraction(self, url, expected_host):
        item = _make_item(link=url)
        card = build_link_card(item)
        assert card is not None
        assert card["hostname"] == expected_host


class TestBuildScrapedPostMetadata:
    def test_combines_source_and_link_card(self):
        source = _make_source()
        item = _make_item()
        meta = build_scraped_post_metadata(source, item)
        assert "source" in meta
        assert "link_card" in meta
        assert meta["source"]["label"] == "Reddit · r/python"
        assert meta["link_card"]["url"] == "https://example.com/post/1"

    def test_omits_link_card_when_item_has_no_link(self):
        source = _make_source()
        item = _make_item(link=None)
        meta = build_scraped_post_metadata(source, item)
        assert "source" in meta
        assert "link_card" not in meta


class TestBuildLinkCardVideoFlag:
    def test_link_card_includes_is_video_false_by_default(self):
        item = _make_item()
        card = build_link_card(item)
        assert card is not None
        assert card["is_video"] is False

    def test_link_card_includes_is_video_true_when_item_is_video(self):
        item = ScrapedItem(
            title="T",
            text="body",
            image_url="https://x/thumb.jpg",
            link="https://x/v",
            popularity=0,
            is_video=True,
        )
        card = build_link_card(item)
        assert card is not None
        assert card["is_video"] is True
