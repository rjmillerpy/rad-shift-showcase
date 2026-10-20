"""Unit tests for app/posts/feeds.py — feed queries + AlgoWeights."""

from dataclasses import FrozenInstanceError

import pytest

from app.posts import feeds
from app.posts.feeds import AlgoWeights


class TestAlgoWeights:
    def test_defaults(self):
        w = AlgoWeights.from_settings(None)
        assert w.like == 1.0
        assert w.repost == 1.0
        assert w.share == 1.0
        assert w.laugh == 0.5
        assert w.save == 0.5
        assert w.slop == 0.0
        assert w.recency == 0.3

    def test_empty_dict_gives_defaults(self):
        assert AlgoWeights.from_settings({}) == AlgoWeights()

    def test_settings_override_all_weights(self):
        w = AlgoWeights.from_settings(
            {
                "like_weight": 2.0,
                "repost_weight": 3.0,
                "share_weight": 4.0,
                "laugh_weight": 5.0,
                "save_weight": 6.0,
                "slop_weight": 7.0,
                "recency_weight": 8.0,
            }
        )
        assert (w.like, w.repost, w.share, w.laugh, w.save, w.slop, w.recency) == (
            2.0,
            3.0,
            4.0,
            5.0,
            6.0,
            7.0,
            8.0,
        )

    def test_string_numbers_coerced(self):
        w = AlgoWeights.from_settings({"like_weight": "2.5"})
        assert w.like == 2.5

    def test_immutable(self):
        w = AlgoWeights()
        with pytest.raises(FrozenInstanceError):
            w.like = 42


class TestGetAllPostsFormatted:
    def test_empty_returns_empty_list(self, db_session):
        posts, has_more = feeds.get_all_posts_formatted(db=db_session)
        assert posts == []
        assert has_more is False

    def test_returns_posts_in_reverse_time(
        self,
        create_user,
        create_post,
        db_session,
    ):
        user = create_user(username="feed_time")
        older = create_post(user=user, text="older", unix_timestamp=100)
        newer = create_post(user=user, text="newer", unix_timestamp=200)
        posts, _ = feeds.get_all_posts_formatted(db=db_session)
        assert [p.id for p in posts[:2]] == [newer.id, older.id]

    def test_has_more_signals_when_over_limit(
        self,
        create_user,
        create_post,
        db_session,
    ):
        user = create_user(username="feed_more")
        for i in range(3):
            create_post(user=user, text=f"p{i}", unix_timestamp=100 + i)
        posts, has_more = feeds.get_all_posts_formatted(db=db_session, limit=2)
        assert len(posts) == 2
        assert has_more is True

    def test_excludes_drafts(self, create_user, create_post, db_session):
        user = create_user(username="feed_drafts")
        create_post(user=user, text="live", is_draft=False)
        create_post(user=user, text="draft", is_draft=True)
        posts, _ = feeds.get_all_posts_formatted(db=db_session)
        assert [p.text for p in posts] == ["live"]

    def test_excludes_replies(self, create_user, create_post, db_session):
        user = create_user(username="feed_replies")
        parent = create_post(user=user, text="parent")
        create_post(user=user, text="reply", is_reply=True, parent_post_id=parent.id)
        posts, _ = feeds.get_all_posts_formatted(db=db_session)
        texts = [p.text for p in posts]
        assert "reply" not in texts


class TestGetAlgoPostsFormatted:
    def test_uses_algo_weights_when_engagement_enabled(
        self,
        create_user,
        create_post,
        db_session,
    ):
        user = create_user(username="feed_algo")
        user.algo_settings = {"engagement_enabled": True, "like_weight": 1.0}
        db_session.commit()
        low = create_post(user=user, text="low")
        low.likes = 0
        high = create_post(user=user, text="high")
        high.likes = 100
        db_session.commit()

        posts, _ = feeds.get_algo_posts_formatted(db=db_session, current_user=user)
        assert posts[0].id == high.id

    def test_pure_chronological_when_engagement_disabled(
        self,
        create_user,
        create_post,
        db_session,
    ):
        user = create_user(username="feed_algo_off")
        user.algo_settings = {"engagement_enabled": False}
        db_session.commit()
        older = create_post(user=user, text="older", unix_timestamp=100)
        newer = create_post(user=user, text="newer", unix_timestamp=200)
        posts, _ = feeds.get_algo_posts_formatted(db=db_session, current_user=user)
        assert posts[0].id == newer.id
        assert posts[1].id == older.id


class TestGetSavedPostsFormatted:
    def test_empty_when_no_saves(self, create_user, db_session):
        user = create_user(username="feed_saved_empty")
        assert feeds.get_saved_posts_formatted(user, db_session) == []

    def test_returns_saved_and_marks_saved_flag(
        self,
        create_user,
        create_post,
        db_session,
    ):
        from app.posts.models import PostSave

        author = create_user(username="feed_saved_author")
        reader = create_user(username="feed_saved_reader")
        post = create_post(user=author)
        db_session.add(PostSave(user_id=reader.id, post_id=post.id))
        db_session.commit()

        results = feeds.get_saved_posts_formatted(reader, db_session)
        assert len(results) == 1
        assert results[0].is_saved_by_me is True


class TestGetUserDraftsFormatted:
    def test_returns_only_drafts(self, create_user, create_post, db_session):
        user = create_user(username="feed_drafts_only")
        create_post(user=user, text="live", is_draft=False)
        create_post(user=user, text="draft1", is_draft=True)
        create_post(user=user, text="draft2", is_draft=True)
        drafts = feeds.get_user_drafts_formatted(user, db_session)
        assert {d.text for d in drafts} == {"draft1", "draft2"}


class TestGetSinglePostFormatted:
    def test_none_when_missing(self, db_session):
        assert feeds.get_single_post_formatted(999_999, db_session) is None

    def test_returns_response(self, create_user, create_post, db_session):
        user = create_user(username="feed_single")
        post = create_post(user=user, text="one")
        result = feeds.get_single_post_formatted(post.id, db_session)
        assert result is not None
        assert result.id == post.id
