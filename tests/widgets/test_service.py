"""Tests for app/widgets/service.py — widget CRUD, review pipeline, installs, ratings."""

import pytest
from fastapi import HTTPException

from app.widgets import service
from app.widgets.models import Widget, WidgetInstall


def _widget_payload(**overrides) -> dict:
    base = {
        "title": "My Widget",
        "category": "tool",
        "language": "javascript",
        "code": "console.log('hi')",
        "description": "desc",
    }
    base.update(overrides)
    return base


@pytest.fixture()
def author(create_user):
    return create_user(username="author")


@pytest.fixture()
def other(create_user):
    return create_user(username="other")


@pytest.fixture()
def admin(create_user):
    return create_user(username="w_admin", is_admin=True)


class TestCreateWidget:
    def test_creates_draft(self, author, db_session):
        result = service.create_widget(author, _widget_payload(), db_session)
        assert result["status"] == "draft"
        assert result["title"] == "My Widget"
        assert result["author_id"] == author.id

    @pytest.mark.parametrize(
        "field,value",
        [("category", "not_a_category"), ("language", "not_a_language")],
        ids=["bad-category", "bad-language"],
    )
    def test_rejects_invalid_enum(self, author, db_session, field, value):
        payload = _widget_payload(**{field: value})
        with pytest.raises(HTTPException) as exc:
            service.create_widget(author, payload, db_session)
        assert exc.value.status_code == 400


class TestUpdateDeleteWidget:
    def test_author_can_update_own_draft(self, author, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        updated = service.update_widget(author, w["id"], {"title": "New"}, db_session)
        assert updated["title"] == "New"

    def test_non_author_cannot_update(self, author, other, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        with pytest.raises(HTTPException) as exc:
            service.update_widget(other, w["id"], {"title": "hack"}, db_session)
        assert exc.value.status_code in (403, 404)

    def test_delete_removes_widget(self, author, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        service.delete_widget(author, w["id"], db_session)
        assert db_session.query(Widget).filter_by(id=w["id"]).first() is None


class TestSubmitAndReview:
    def test_submit_sets_status(self, author, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        result = service.submit_for_review(author, w["id"], db_session)
        assert result["status"] in ("submitted", "under_review")

    def test_admin_approves(self, author, admin, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        service.submit_for_review(author, w["id"], db_session)
        result = service.review_widget(admin, w["id"], "approve", None, db_session)
        assert result["status"] == "approved"

    def test_admin_rejects(self, author, admin, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        service.submit_for_review(author, w["id"], db_session)
        result = service.review_widget(admin, w["id"], "reject", "no", db_session)
        assert result["status"] == "rejected"

    def test_invalid_review_action_400(self, author, admin, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        service.submit_for_review(author, w["id"], db_session)
        with pytest.raises(HTTPException) as exc:
            service.review_widget(admin, w["id"], "nuke", None, db_session)
        assert exc.value.status_code == 400


class TestInstallUninstall:
    def _make_approved(self, author, admin, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        service.submit_for_review(author, w["id"], db_session)
        service.review_widget(admin, w["id"], "approve", None, db_session)
        return w

    def test_install_creates_row_and_bumps_count(self, author, admin, other, db_session):
        w = self._make_approved(author, admin, db_session)
        service.install_widget(other, w["id"], db_session)
        assert db_session.query(WidgetInstall).filter_by(widget_id=w["id"]).count() == 1
        db_session.refresh(db_session.query(Widget).filter_by(id=w["id"]).one())
        widget = db_session.query(Widget).filter_by(id=w["id"]).one()
        assert widget.install_count == 1

    def test_uninstall_removes_row(self, author, admin, other, db_session):
        w = self._make_approved(author, admin, db_session)
        service.install_widget(other, w["id"], db_session)
        service.uninstall_widget(other, w["id"], db_session)
        assert db_session.query(WidgetInstall).filter_by(widget_id=w["id"]).count() == 0


class TestRateWidget:
    def test_valid_rating_persists(self, author, admin, other, db_session):
        w = service.create_widget(author, _widget_payload(), db_session)
        service.submit_for_review(author, w["id"], db_session)
        service.review_widget(admin, w["id"], "approve", None, db_session)
        result = service.rate_widget(other, w["id"], 5, "great", db_session)
        assert result.get("rating") == 5 or result.get("status") == "rated"

    @pytest.mark.parametrize("rating", [0, 6, -1, 100], ids=["zero", "six", "neg", "huge"])
    def test_rejects_out_of_range_rating(self, author, admin, other, db_session, rating):
        w = service.create_widget(author, _widget_payload(), db_session)
        service.submit_for_review(author, w["id"], db_session)
        service.review_widget(admin, w["id"], "approve", None, db_session)
        with pytest.raises(HTTPException) as exc:
            service.rate_widget(other, w["id"], rating, None, db_session)
        assert exc.value.status_code == 400
