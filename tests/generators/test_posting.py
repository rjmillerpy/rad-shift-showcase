"""Tests for app/generators/posting.py — write filtered items as posts."""

import json

import pytest
from fastapi import HTTPException

from app.generators import posting
from app.generators.items import ScrapedItem
from app.generators.models import GeneratorProfile, GeneratorSource
from app.generators.posting import (
    CONTINUATION_MARKER,
    MAX_POST_TEXT_CHARS,
    SCRAPED_BODY_MAX_WITH_LINK,
    _build_post_text,
    strip_markdown,
)
from app.posts.models import PostModel


class TestStripMarkdown:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("**bold text**", "bold text"),
            ("*italic*", "italic"),
            ("_italic_", "italic"),
            ("~~strike~~", "strike"),
            ("`code`", "code"),
            ("# Heading", "Heading"),
            ("## Sub heading", "Sub heading"),
            ("[label](https://example.com)", "label"),
            ("[https://x.com](https://x.com)", "https://x.com"),
            ("* item one\n* item two", "• item one\n• item two"),
            ("- dash bullet", "• dash bullet"),
            ("**Kaggle Link:** [foo](https://x)", "Kaggle Link: foo"),
            ("plain text stays plain", "plain text stays plain"),
            ("`open_time` of `1m` candles", "open_time of 1m candles"),
        ],
        ids=[
            "bold",
            "italic-ast",
            "italic-und",
            "strike",
            "code",
            "heading-h1",
            "heading-h2",
            "link-simple",
            "link-url-as-text",
            "bullet-asterisk",
            "bullet-dash",
            "bold-then-link",
            "plain",
            "multiple-code-spans",
        ],
    )
    def test_strips_common_markdown(self, raw, expected):
        assert strip_markdown(raw) == expected

    def test_empty_string_is_safe(self):
        assert strip_markdown("") == ""

    def test_none_is_safe(self):
        # The helper is robust against pass-through of empty/None-ish values.
        assert strip_markdown("") == ""

    def test_preserves_newlines(self):
        result = strip_markdown("Line one\n\nLine two")
        assert result == "Line one\n\nLine two"

    def test_does_not_mangle_loose_asterisks(self):
        """An unpaired asterisk shouldn't be treated as italic."""
        assert strip_markdown("a * b") == "a * b"


class TestBuildPostText:
    def test_drops_title_prefix_when_link_present(self):
        item = ScrapedItem(
            title="Post title",
            text="Some body text",
            image_url=None,
            link="https://x.com",
            popularity=0,
        )
        body = _build_post_text(item)
        assert body == "Some body text"

    def test_prepends_title_when_no_link(self):
        item = ScrapedItem(
            title="Post title",
            text="Some body text",
            image_url=None,
            link=None,
            popularity=0,
        )
        body = _build_post_text(item)
        assert body.startswith("Post title")
        assert "Some body text" in body

    def test_caps_long_body_with_continuation_marker_when_link_present(self):
        long_body = "x" * 2000
        item = ScrapedItem(
            title="t",
            text=long_body,
            image_url=None,
            link="https://x.com",
            popularity=0,
        )
        body = _build_post_text(item)
        assert len(body) <= SCRAPED_BODY_MAX_WITH_LINK
        assert body.endswith(CONTINUATION_MARKER)

    def test_does_not_cap_at_link_threshold_when_no_link(self):
        body_text = "x" * 1500
        item = ScrapedItem(
            title=None,
            text=body_text,
            image_url=None,
            link=None,
            popularity=0,
        )
        body = _build_post_text(item)
        # No-link items get the full 5000-char cap, so 1500 passes through untouched.
        assert body == body_text
        assert len(body) <= MAX_POST_TEXT_CHARS

    def test_strips_markdown_from_body(self):
        item = ScrapedItem(
            title=None,
            text="**Bold** with [link](https://x) and `code`",
            image_url=None,
            link="https://reddit.com/x",
            popularity=0,
        )
        body = _build_post_text(item)
        assert "**" not in body
        assert "`" not in body
        assert "Bold" in body
        assert "link" in body
        assert "code" in body


def _make_item(**overrides) -> ScrapedItem:
    defaults = {
        "title": "Post title",
        "text": "Body text",
        "image_url": None,
        "link": "https://example.com/x",
        "popularity": 10,
    }
    defaults.update(overrides)
    return ScrapedItem(**defaults)


@pytest.fixture
def reddit_source_with_profile(db_session, create_user):
    bot = create_user(username="posting_bot")
    source = GeneratorSource(
        name="r/python",
        site_url="https://reddit.com/r/python",
        platform="reddit",
        platform_config={"subreddit": "python"},
        config={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
    db_session.commit()
    return source, bot


class TestPostFilteredItems:
    def test_no_active_profile_raises_400(self, db_session):
        source = GeneratorSource(
            name="orphan",
            site_url="https://x.com",
            platform="reddit",
            platform_config={"subreddit": "x"},
            config={},
        )
        db_session.add(source)
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            posting.post_filtered_items(source, [_make_item()], db_session)
        assert exc.value.status_code == 400

    def test_creates_post_with_source_metadata_attached(
        self, reddit_source_with_profile, db_session
    ):
        source, bot = reddit_source_with_profile
        posted = posting.post_filtered_items(source, [_make_item()], db_session)
        assert posted == 1

        post = (
            db_session.query(PostModel)
            .filter_by(user_id=bot.id)
            .order_by(PostModel.id.desc())
            .first()
        )
        assert post is not None
        # post_metadata is stored as a JSON string in the column
        meta = json.loads(post.post_metadata)
        assert meta["source"]["platform"] == "reddit"
        assert meta["source"]["label"] == "Reddit · r/python"
        assert meta["link_card"]["url"] == "https://example.com/x"
        assert meta["link_card"]["hostname"] == "example.com"

    def test_post_text_does_not_have_bare_url_trailer(self, reddit_source_with_profile, db_session):
        """Regression: the bare URL used to be appended to text; now it lives on the card."""
        source, bot = reddit_source_with_profile
        posting.post_filtered_items(
            source, [_make_item(link="https://my-link.example/post/42")], db_session
        )
        post = (
            db_session.query(PostModel)
            .filter_by(user_id=bot.id)
            .order_by(PostModel.id.desc())
            .first()
        )
        assert "https://my-link.example/post/42" not in post.text

    def test_dedupes_against_existing_user_posts(self, reddit_source_with_profile, db_session):
        source, bot = reddit_source_with_profile
        items = [
            _make_item(title="t1", text="Same body"),
            _make_item(title="t2", text="Same body"),  # dup text
            _make_item(title="t3", text="Different body"),
        ]
        posted = posting.post_filtered_items(source, items, db_session)
        assert posted == 2

    def test_item_without_link_still_posts_without_link_card(
        self, reddit_source_with_profile, db_session
    ):
        source, bot = reddit_source_with_profile
        posted = posting.post_filtered_items(source, [_make_item(link=None)], db_session)
        assert posted == 1
        post = (
            db_session.query(PostModel)
            .filter_by(user_id=bot.id)
            .order_by(PostModel.id.desc())
            .first()
        )
        meta = json.loads(post.post_metadata)
        assert "link_card" not in meta
        assert "source" in meta
