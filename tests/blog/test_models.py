"""Tests for app/blog/models.py — BlogPost / BlogView ORM."""

import time

import pytest
from sqlalchemy.exc import IntegrityError

from app.blog.models import BlogPost, BlogView


def _make_blog(user_id: int, **overrides) -> BlogPost:
    base = {
        "user_id": user_id,
        "slug": "hello-world",
        "title": "Hello",
        "content_html": "<p>Hi</p>",
        "created_at": int(time.time()),
    }
    base.update(overrides)
    return BlogPost(**base)


class TestBlogPost:
    def test_defaults(self, db_session, create_user):
        user = create_user(username="author1")
        db_session.add(_make_blog(user.id))
        db_session.commit()

        row = db_session.query(BlogPost).filter_by(user_id=user.id).one()
        assert row.is_draft is True
        assert row.is_published is False
        assert row.monetized is False
        assert row.ad_placement == "none"
        assert row.reading_time_minutes == 1
        assert row.view_count == 0

    def test_slug_uniqueness(self, db_session, create_user):
        user = create_user(username="author2")
        db_session.add(_make_blog(user.id, slug="dup"))
        db_session.commit()

        db_session.add(_make_blog(user.id, slug="dup"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestBlogView:
    def test_view_row_insert(self, db_session, create_user):
        user = create_user(username="reader1")
        blog = _make_blog(user.id, slug="view-test")
        db_session.add(blog)
        db_session.commit()

        db_session.add(
            BlogView(
                blog_post_id=blog.id,
                user_id=user.id,
                view_timestamp=int(time.time()),
                read_time_seconds=30,
            )
        )
        db_session.commit()

        view = db_session.query(BlogView).filter_by(blog_post_id=blog.id).one()
        assert view.read_time_seconds == 30
