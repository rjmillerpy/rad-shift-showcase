"""Slop ranking (app/posts/slop.py) on real posts, flags and feeds."""

import time

import pytest

from app.engagement.models import PostTrending
from app.posts.models import Slop
from app.posts.slop import AI_LESS, AI_SHOW, FLOAT, SINK, UNSORTED, rank_keys, slop_ordering


@pytest.fixture()
def author(create_user):
    return create_user(username="author")


@pytest.fixture()
def flaggers(create_user):
    return [create_user(username=f"flagger{i}") for i in range(3)]


def _sunk(post_ids, ai_content, db):
    """Which of these posts the default ordering sinks."""
    return {pid for pid, key in rank_keys(post_ids, SINK, ai_content, db).items() if key == 1}


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
        assert _sunk([post.id], AI_SHOW, db_session) == set()

    def test_three_flags_and_no_likes_sinks_it(self, db_session, author, create_post, flaggers):
        post = create_post(author)
        _flag(db_session, post, flaggers)
        assert _sunk([post.id], AI_SHOW, db_session) == {post.id}

    def test_three_flags_dont_sink_a_post_with_fifty_likes(
        self, db_session, author, create_post, flaggers
    ):
        post = create_post(author)
        post.likes = 50
        _flag(db_session, post, flaggers)
        assert _sunk([post.id], AI_SHOW, db_session) == set()

    def test_flags_from_before_a_dismissal_dont_count(
        self, db_session, author, create_post, flaggers
    ):
        post = create_post(author)
        _flag(db_session, post, flaggers, when=1_000)
        post.slop_cleared_at = 2_000
        db_session.commit()
        assert _sunk([post.id], AI_SHOW, db_session) == set()

    def test_ai_labelled_posts_sink_only_for_readers_who_chose_less(
        self, db_session, author, create_post
    ):
        post = create_post(author)
        post.ai_label = "author"
        db_session.commit()
        assert _sunk([post.id], AI_SHOW, db_session) == set()
        assert _sunk([post.id], AI_LESS, db_session) == {post.id}

    def test_no_posts_no_query(self, db_session):
        assert _sunk([], AI_SHOW, db_session) == set()


class TestOrdering:
    @pytest.mark.parametrize(
        ("settings", "ordering"),
        [
            (None, SINK),
            ({"slop_filter": "hide"}, SINK),
            ({"slop_filter": "dim"}, SINK),
            ({"sink_community_slop": False}, UNSORTED),
            ({"slop_filter": "show"}, UNSORTED),
            ({"slop_filter": "only"}, UNSORTED),
            ({"slop_filter": "all_slop"}, FLOAT),
            ({"slop_filter": "all_slop", "sink_community_slop": False}, FLOAT),
        ],
    )
    def test_settings_pick_the_ordering(self, settings, ordering):
        assert slop_ordering(settings) == ordering

    def test_unsorted_still_sinks_ai_posts_for_readers_who_chose_less(
        self, db_session, author, create_post, flaggers
    ):
        slop, ai = create_post(author), create_post(author)
        ai.ai_label = "author"
        _flag(db_session, slop, flaggers)
        assert rank_keys([slop.id, ai.id], UNSORTED, AI_LESS, db_session) == {
            slop.id: 0,
            ai.id: 1,
        }

    def test_float_ranks_the_sloppiest_first(self, db_session, author, create_post, flaggers):
        clean, mild, worst = create_post(author), create_post(author), create_post(author)
        _flag(db_session, mild, flaggers[:1])
        _flag(db_session, worst, flaggers)
        keys = rank_keys([clean.id, mild.id, worst.id], FLOAT, AI_SHOW, db_session)
        assert sorted(keys, key=keys.__getitem__) == [worst.id, mild.id, clean.id]


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
        # Randomness off: these tests are about where slop lands, not the shuffle.
        reader.algo_settings = {"randomness": 0, **settings}
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

    def test_turning_sinking_off_leaves_slop_in_the_feeds_order(
        self, client, three_posts, create_user, auth_header, db_session
    ):
        headers = self._reader(create_user, auth_header, db_session, sink_community_slop=False)
        assert self._texts(client, "/posts/algo", headers) == ["ai", "slop", "plain"]

    def test_show_doesnt_sink_slop(self, client, three_posts, create_user, auth_header, db_session):
        headers = self._reader(create_user, auth_header, db_session, slop_filter="show")
        assert self._texts(client, "/posts/algo", headers) == ["ai", "slop", "plain"]

    def test_only_keeps_the_feeds_order_among_slop(
        self, client, db_session, three_posts, create_user, auth_header, flaggers
    ):
        """Before: the slop-only feed sank its own worst slop under milder slop."""
        plain, _slop, _ai = three_posts
        _flag(db_session, plain, flaggers[:1])
        headers = self._reader(
            create_user, auth_header, db_session, slop_filter="only", slop_threshold=1
        )
        assert self._texts(client, "/posts/algo", headers) == ["slop", "plain"]

    def test_all_slop_floats_slop_to_the_top_and_shows_the_rest(
        self, client, three_posts, create_user, auth_header, db_session
    ):
        headers = self._reader(create_user, auth_header, db_session, slop_filter="all_slop")
        assert self._texts(client, "/posts/algo", headers) == ["slop", "ai", "plain"]

    def test_all_slop_shows_posts_the_reader_flagged(
        self, client, db_session, three_posts, create_user, auth_header
    ):
        """ "hide" drops the reader's own flagged posts; "all_slop" keeps them."""
        plain, _slop, _ai = three_posts
        headers = self._reader(create_user, auth_header, db_session, slop_filter="all_slop")
        assert (
            client.post(
                f"/posts/slop/{plain.id}", json={"reason": "AI slop"}, headers=headers
            ).status_code
            == 200
        )
        assert "plain" in self._texts(client, "/posts/algo", headers)

    def test_chronological_feed_sinks_slop_too(
        self, client, three_posts, create_user, auth_header, db_session
    ):
        headers = self._reader(create_user, auth_header, db_session, engagement_enabled=False)
        assert self._texts(client, "/posts/algo", headers) == ["ai", "plain", "slop"]

    def test_all_slop_floats_slop_to_the_top_of_trending(
        self, client, db_session, three_posts, create_user, auth_header
    ):
        plain, slop, ai = three_posts
        now = time.time()
        for post, score in ((plain, 30.0), (ai, 20.0), (slop, 10.0)):
            db_session.add(PostTrending(post_id=post.id, score=score, updated_at=now))
        db_session.commit()
        headers = self._reader(create_user, auth_header, db_session, slop_filter="all_slop")
        assert self._texts(client, "/posts/trending", headers) == ["slop", "plain", "ai"]

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
