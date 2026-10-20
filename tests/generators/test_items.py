"""Tests for app/generators/items.py — ScrapedItem and filter_items."""

from app.generators.items import ScrapedItem, filter_items

# ── filter_items ────────────────────────────────────────────────────────


def _make_items() -> list[ScrapedItem]:
    """Create a known list of items for filter tests."""
    return [
        ScrapedItem(
            title="Python Tutorial",
            text="Learn python basics",
            image_url=None,
            link=None,
            popularity=500,
        ),
        ScrapedItem(
            title="Rust Guide",
            text="Intro to rust programming",
            image_url=None,
            link=None,
            popularity=1200,
        ),
        ScrapedItem(
            title="Go Tips", text="Golang tips and tricks", image_url=None, link=None, popularity=50
        ),
        ScrapedItem(
            title="Java News",
            text="Java updates for enterprise",
            image_url=None,
            link=None,
            popularity=300,
        ),
        ScrapedItem(
            title="NSFW Content",
            text="Explicit spam material",
            image_url=None,
            link=None,
            popularity=900,
        ),
    ]


class TestFilterItems:
    def test_no_filters_returns_sorted_by_popularity(self):
        items = _make_items()
        result = filter_items(items)
        assert result[0].popularity == 1200
        assert result[-1].popularity == 50

    def test_min_popularity(self):
        items = _make_items()
        result = filter_items(items, min_popularity=300)
        assert all(i.popularity >= 300 for i in result)
        # Items with popularity >= 300: 1200, 900, 500, 300 => 4 items
        assert len(result) == 4

    def test_include_keywords(self):
        items = _make_items()
        result = filter_items(items, include_keywords=["python", "rust"])
        assert len(result) == 2
        titles = {i.title for i in result}
        assert "Python Tutorial" in titles
        assert "Rust Guide" in titles

    def test_exclude_keywords(self):
        items = _make_items()
        result = filter_items(items, exclude_keywords=["spam", "nsfw"])
        assert all("spam" not in i.text.lower() for i in result)
        assert len(result) == 4

    def test_max_items(self):
        items = _make_items()
        result = filter_items(items, max_items=2)
        assert len(result) == 2
        assert result[0].popularity == 1200
        assert result[1].popularity == 900

    def test_combined_filters(self):
        items = _make_items()
        result = filter_items(
            items,
            min_popularity=100,
            exclude_keywords=["spam"],
            max_items=2,
        )
        assert len(result) == 2
        assert result[0].popularity == 1200

    def test_empty_input(self):
        result = filter_items([])
        assert result == []

    def test_include_keywords_case_insensitive(self):
        items = _make_items()
        result = filter_items(items, include_keywords=["PYTHON"])
        assert len(result) == 1
        assert result[0].title == "Python Tutorial"


# ── fetch_page ──────────────────────────────────────────────────────────
