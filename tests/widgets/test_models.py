"""Tests for app/widgets/models.py — Widget / Install / Review / Template ORM."""

import time

import pytest
from sqlalchemy.exc import IntegrityError

from app.widgets.models import Widget, WidgetInstall, WidgetReview, WidgetTemplate


def _make_widget(author_id: int, **overrides) -> Widget:
    base = {
        "author_id": author_id,
        "title": "T",
        "category": "tool",
        "language": "javascript",
        "code": "x",
        "created_at": int(time.time()),
    }
    base.update(overrides)
    return Widget(**base)


class TestWidgetDefaults:
    def test_defaults_populated(self, db_session, create_user):
        author = create_user(username="coder")
        w = _make_widget(author.id)
        db_session.add(w)
        db_session.commit()
        db_session.refresh(w)
        assert w.status == "draft"
        assert w.version == "1.0.0"
        assert w.execution_mode == "client"
        assert w.install_count == 0
        assert w.default_width == 400
        assert w.resizable is False


class TestUniqueConstraints:
    def test_install_unique_per_user_widget(self, db_session, create_user):
        author = create_user(username="a1")
        w = _make_widget(author.id)
        db_session.add(w)
        db_session.commit()

        db_session.add(WidgetInstall(user_id=author.id, widget_id=w.id, installed_at=1))
        db_session.commit()

        db_session.add(WidgetInstall(user_id=author.id, widget_id=w.id, installed_at=2))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_review_unique_per_user_widget(self, db_session, create_user):
        author = create_user(username="a2")
        w = _make_widget(author.id)
        db_session.add(w)
        db_session.commit()

        db_session.add(WidgetReview(user_id=author.id, widget_id=w.id, rating=5, created_at=1))
        db_session.commit()

        db_session.add(WidgetReview(user_id=author.id, widget_id=w.id, rating=3, created_at=2))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestWidgetTemplate:
    def test_template_insert(self, db_session):
        tpl = WidgetTemplate(
            name="Sample",
            category="tool",
            language="html",
            description="x",
            starter_code="<html></html>",
        )
        db_session.add(tpl)
        db_session.commit()
        db_session.refresh(tpl)
        assert tpl.id is not None
