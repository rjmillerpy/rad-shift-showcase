"""Slop ranking (app/posts/slop.py) on real posts, flags and feeds."""

import time

import pytest

from app.engagement.models import PostTrending
from app.posts.models import Slop
from app.posts.slop import AI_LESS, AI_SHOW, demoted_ids


@pytest.fixture()
def author(create_user):
    return create_user(username="author")


@pytest.fixture()
def flaggers(create_user):
    return [create_user(username=f"flagger{i}") for i in range(3)]


def _flag(db, post, users, when=None):
    for user in users:
        db.add(
            Slop(
                user_id=user.id,
                post_id=post.id,
                reason="AI slop",
                unix_timestamp=when or int(time.time()),
            )
        )
    db.commit()


class TestThresholds:
    """The examples in app/posts/slop.py's docstring."""

    def test_one_flag_on_a_new_post_doesnt_sink_it(self, db_session, author, create_post, flaggers):
        post = create_post(author)
        _flag(db_session, post, flaggers[:1])
        assert demoted_ids([post.id], AI_SHOW, db_session) == set()

    def test_three_flags_and_no_likes_sinks_it(self, db_session, author, create_post, flaggers):
        post = create_post(author)
        _flag(db_session, post, flaggers)
        assert demoted_ids([post.id], AI_SHOW, db_session) == {post.id}

    def test_three_flags_dont_sink_a_post_with_fifty_likes(
        self, db_session, author, create_post, flaggers
    ):
        post = create_post(author)
        post.likes = 50
        _flag(db_session, post, flaggers)
        assert demoted_ids([post.id], AI_SHOW, db_session) == set()

    def test_flags_from_before_a_dismissal_dont_count(
        self, db_session, author, create_post, flaggers
    ):
        post = create_post(author)
        _flag(db_session, post, flaggers, when=1_000)
        post.slop_cleared_at = 2_000
        db_session.commit()
        assert demoted_ids([post.id], AI_SHOW, db_session) == set()

    def test_ai_labelled_posts_sink_only_for_readers_who_chose_less(
        self, db_session, author, create_post
    ):
        post = create_post(author)
        post.ai_label = "author"
        db_session.commit()
        assert demoted_ids([post.id], AI_SHOW, db_session) == set()
        assert demoted_ids([post.id], AI_LESS, db_session) == {post.id}

    def test_no_posts_no_query(self, db_session):
        assert demoted_ids([], AI_SHOW, db_session) == set()


class TestFeeds:
    @pytest.fixture()
    def three_posts(self, db_session, author, create_post, flaggers):
        """Oldest to newest: plain, slop (flagged by three, no likes), AI-labelled."""
        now = int(time.time())
        plain = create_post(author, text="plain", unix_timestamp=now - 300)
        slop = create_post(author, text="slop", unix_timestamp=now - 200)
        ai = create_post(author, text="ai", unix_timestamp=now - 100)
        ai.ai_label = "author"
        _flag(db_session, slop, flaggers)
        return plain, slop, ai

    def _reader(self, create_user, auth_header, db_session, **settings):
        reader = create_user(username="reader")
        reader.algo_settings = settings or None
        db_session.commit()
        return auth_header("reader")

    def _texts(self, client, path, headers):
        return [post["text"] for post in client.get(path, headers=headers).json()["posts"]]

    def test_slop_sinks_to_the_bottom_of_the_algorithmic_feed(
        self, client, three_posts, create_user, auth_header, db_session
    ):
        headers = self._reader(create_user, auth_header, db_session)
        assert self._texts(client, "/posts/algo", headers) == ["ai", "plain", "slop"]

    def test_ai_less_sinks_ai_posts_too(
        self, client, three_posts, create_user, auth_header, db_session
    ):
        headers = self._reader(create_user, auth_header, db_session, ai_content="less")
        assert self._texts(client, "/posts/algo", headers)[0] == "plain"

    def test_ai_hide_leaves_them_out(
        self, client, three_posts, create_user, auth_header, db_session
    ):
        headers = self._reader(create_user, auth_header, db_session, ai_content="hide")
        assert self._texts(client, "/posts/algo", headers) == ["plain", "slop"]

    def test_an_unknown_ai_setting_means_show(
        self, client, three_posts, create_user, auth_header, db_session
    ):
        headers = self._reader(create_user, auth_header, db_session, ai_content="banana")
        assert "ai" in self._texts(client, "/posts/algo", headers)

    def test_slop_sinks_to_the_bottom_of_trending(self, client, db_session, three_posts):
        plain, slop, ai = three_posts
        now = time.time()
        # Slop scores highest, so trending alone would put it first.
        for post, score in ((slop, 30.0), (plain, 20.0), (ai, 10.0)):
            db_session.add(PostTrending(post_id=post.id, score=score, updated_at=now))
        db_session.commit()
        assert self._texts(client, "/posts/trending", {})[-1] == "slop"

    def test_the_following_feed_keeps_its_own_order(
        self, client, three_posts, create_user, auth_header
    ):
        """You chose those people: their posts stay newest first, slop included."""
        create_user(username="follower")
        assert client.post("/follow/author", headers=auth_header("follower")).status_code == 200
        assert self._texts(client, "/posts/following", auth_header("follower")) == [
            "ai",
            "slop",
            "plain",
        ]
