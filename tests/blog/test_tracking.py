"""Tests for app/blog/tracking.py — view records and stats."""

import time

from app.blog import tracking
from app.blog.models import BlogPost, BlogView


def _make_blog(db_session, user, **overrides) -> BlogPost:
    base = {
        "user_id": user.id,
        "slug": f"blog-{user.id}-{int(time.time() * 1_000_000)}",
        "title": "T",
        "content_html": "<p>x</p>",
        "created_at": int(time.time()),
        "is_draft": False,
        "is_published": True,
    }
    base.update(overrides)
    post = BlogPost(**base)
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    return post


class TestRecordBlogView:
    def test_inserts_row_and_increments_counter(self, db_session, create_user):
        author = create_user(username="author")
        post = _make_blog(db_session, author)

        tracking.record_blog_view(post.id, db_session, read_time_seconds=30, ip_hash="abcd")
        db_session.refresh(post)

        views = db_session.query(BlogView).filter_by(blog_post_id=post.id).all()
        assert len(views) == 1
        assert views[0].read_time_seconds == 30
        assert views[0].ip_hash == "abcd"
        assert post.view_count == 1

    def test_multiple_views_increment_counter(self, db_session, create_user):
        author = create_user(username="author2")
        post = _make_blog(db_session, author)

        for _ in range(3):
            tracking.record_blog_view(post.id, db_session)
        db_session.refresh(post)
        assert post.view_count == 3


class TestGetBlogStats:
    def test_empty_for_missing_post(self, db_session):
        assert tracking.get_blog_stats(999_999, db_session) == {}

    def test_aggregates_read_time_and_uniques(self, db_session, create_user):
        author = create_user(username="stat_author")
        reader = create_user(username="stat_reader")
        post = _make_blog(db_session, author)

        tracking.record_blog_view(post.id, db_session, user_id=reader.id, read_time_seconds=10)
        tracking.record_blog_view(post.id, db_session, user_id=reader.id, read_time_seconds=20)
        tracking.record_blog_view(post.id, db_session, user_id=None, read_time_seconds=5)

        stats = tracking.get_blog_stats(post.id, db_session)
        assert stats["view_count"] == 3
        assert stats["total_read_time_seconds"] == 35
        # Anonymous view is excluded from unique reader count
        assert stats["unique_readers"] == 1

    def test_returned_keys(self, db_session, create_user):
        author = create_user(username="stat_keys")
        post = _make_blog(db_session, author)
        tracking.record_blog_view(post.id, db_session)
        stats = tracking.get_blog_stats(post.id, db_session)
        assert set(stats.keys()) == {
            "view_count",
            "total_read_time_seconds",
            "unique_readers",
            "reading_time_minutes",
        }
