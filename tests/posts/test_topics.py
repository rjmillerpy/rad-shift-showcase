"""A post's topics (app/posts/topics.py), and that they're saved when posts are made."""

import json

import pytest

from app.generators import posting
from app.generators.items import ScrapedItem
from app.generators.models import GeneratorProfile, GeneratorSource
from app.posts.models import MAX_TOPIC_LENGTH, PostModel, PostTopic
from app.posts.topics import MAX_TOPICS_PER_POST, metadata_tags, topics_of


class TestTopicsOf:
    def test_tags_then_hashtags_lowercased_without_repeats(self):
        meta = json.dumps({"tags": ["Rust", " Cooking "]})
        assert topics_of("Dinner #cooking and #NBA tonight", meta) == ["rust", "cooking", "nba"]

    def test_the_composers_pipe_separated_tags(self):
        assert topics_of("", {"tags": "a|b| |c"}) == ["a", "b", "c"]

    @pytest.mark.parametrize(
        "text",
        [
            "it&#39;s fine",  # an HTML entity
            "see example.com/page#section",  # a URL fragment
            "##",
            "C# is a language",
        ],
    )
    def test_things_that_arent_hashtags(self, text):
        assert topics_of(text, None) == []

    def test_long_topics_are_cut_and_the_count_capped(self):
        long_tag = "x" * (MAX_TOPIC_LENGTH + 10)
        many = " ".join(f"#t{i}" for i in range(MAX_TOPICS_PER_POST + 5))
        topics = topics_of(many, {"tags": [long_tag]})
        assert topics[0] == "x" * MAX_TOPIC_LENGTH
        assert len(topics) == MAX_TOPICS_PER_POST

    @pytest.mark.parametrize("raw", [None, "", "not json", "[1, 2]", json.dumps({"tags": 5})])
    def test_unusable_metadata_has_no_tags(self, raw):
        assert metadata_tags(raw) == []


class TestSaved:
    def test_a_post_made_through_the_api_gets_its_topics(
        self, client, create_user, auth_header, db_session
    ):
        create_user(username="poster")
        res = client.post(
            "/posts/add",
            data={
                "text": "Weekend #Hiking trip",
                "post_metadata": json.dumps({"tags": "outdoors"}),
            },
            headers=auth_header("poster"),
        )
        assert res.status_code == 200
        assert {t.topic for t in db_session.query(PostTopic)} == {"outdoors", "hiking"}

    def test_scraped_posts_get_their_sources_topics(self, db_session, create_user):
        bot = create_user(username="bot")
        source = GeneratorSource(
            name="r/python",
            site_url="https://reddit.com/r/python",
            platform="reddit",
            platform_config={"subreddit": "python"},
            config={"topics": ["Python", "programming"]},
        )
        db_session.add(source)
        db_session.commit()
        db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
        db_session.commit()
        item = ScrapedItem(
            title="New release", text="Python 3.15 is out", image_url=None, link=None, popularity=1
        )

        assert posting.post_filtered_items(source, [item], db_session) == 1

        post = db_session.query(PostModel).filter_by(user_id=bot.id).one()
        topics = {t.topic for t in db_session.query(PostTopic).filter_by(post_id=post.id)}
        assert topics == {"python", "programming"}

    def test_topics_go_with_their_post(self, db_session, create_user, create_post):
        post = create_post(create_user(username="author"), text="#gone")
        db_session.delete(post)
        db_session.commit()
        assert db_session.query(PostTopic).count() == 0
