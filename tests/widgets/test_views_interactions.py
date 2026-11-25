"""API endpoint tests for widget install/uninstall and rating interactions."""

import pytest

from app.widgets.models import Widget
from tests.widgets._view_helpers import _create_widget, _make_approved_widget


class TestWidgetInstall:
    def test_install_widget(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="installer")
        resp = client.post(
            f"/widgets/{data['id']}/install",
            headers=auth_header("installer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "installed"
        assert body["install_count"] == 1

    def test_install_increments_count(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="u1")
        create_user(username="u2")
        client.post(f"/widgets/{data['id']}/install", headers=auth_header("u1"))
        resp = client.post(f"/widgets/{data['id']}/install", headers=auth_header("u2"))
        assert resp.json()["install_count"] == 2

    def test_cannot_install_twice(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="installer")
        client.post(f"/widgets/{data['id']}/install", headers=auth_header("installer"))
        resp = client.post(f"/widgets/{data['id']}/install", headers=auth_header("installer"))
        assert resp.status_code == 400
        assert "already installed" in resp.json()["detail"].lower()

    def test_cannot_install_unapproved(self, client, create_user, auth_header):
        create_user(username="author")
        create_user(username="installer")
        data = _create_widget(client, auth_header, "author")  # draft
        resp = client.post(
            f"/widgets/{data['id']}/install",
            headers=auth_header("installer"),
        )
        assert resp.status_code == 404

    def test_uninstall_widget(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="installer")
        client.post(f"/widgets/{data['id']}/install", headers=auth_header("installer"))
        resp = client.delete(
            f"/widgets/{data['id']}/install",
            headers=auth_header("installer"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "uninstalled"

    def test_uninstall_decrements_count(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="u1")
        create_user(username="u2")
        client.post(f"/widgets/{data['id']}/install", headers=auth_header("u1"))
        client.post(f"/widgets/{data['id']}/install", headers=auth_header("u2"))
        client.delete(f"/widgets/{data['id']}/install", headers=auth_header("u1"))
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        db_session.refresh(w)
        assert w.install_count == 1

    def test_uninstall_not_installed(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="installer")
        resp = client.delete(
            f"/widgets/{data['id']}/install",
            headers=auth_header("installer"),
        )
        assert resp.status_code == 404

    def test_list_installed(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="installer")
        client.post(f"/widgets/{data['id']}/install", headers=auth_header("installer"))
        resp = client.get("/widgets/installed", headers=auth_header("installer"))
        assert resp.status_code == 200
        widget_ids = [w["id"] for w in resp.json()["widgets"]]
        assert data["id"] in widget_ids

    def test_list_installed_empty(self, client, create_user, auth_header):
        create_user(username="user")
        resp = client.get("/widgets/installed", headers=auth_header("user"))
        assert resp.status_code == 200
        assert resp.json()["widgets"] == []

    def test_install_requires_auth(self, client):
        resp = client.post("/widgets/1/install")
        assert resp.status_code == 401


class TestWidgetRating:
    def _rate(self, client, headers, widget_id, rating):
        return client.post(f"/widgets/{widget_id}/rate", json={"rating": rating}, headers=headers)

    def test_rate_widget(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="rater")
        resp = self._rate(client, auth_header("rater"), data["id"], 5)
        assert resp.status_code == 200
        assert (resp.json()["status"], resp.json()["rating"]) == ("created", 5)

    def test_update_rating(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="rater")
        self._rate(client, auth_header("rater"), data["id"], 3)
        resp = self._rate(client, auth_header("rater"), data["id"], 5)
        assert (resp.json()["status"], resp.json()["rating"]) == ("updated", 5)

    def test_stars_alone_keep_the_review_text(self, client, create_user, auth_header, db_session):
        """Known bug: rating with stars only wiped the written review."""
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        create_user(username="rater")
        client.post(
            f"/widgets/{data['id']}/reviews",
            json={"text": "Great widget!", "rating": 3},
            headers=auth_header("rater"),
        )
        resp = self._rate(client, auth_header("rater"), data["id"], 5)
        assert resp.json()["comment"] == "Great widget!"

    @pytest.mark.parametrize("rating", [0, -1, 6, 100], ids=["zero", "negative", "six", "hundred"])
    def test_rate_invalid_rating(self, client, create_user, auth_header, rating):
        create_user(username="rater")
        assert self._rate(client, auth_header("rater"), 1, rating).status_code == 422

    def test_rate_unapproved_widget(self, client, create_user, auth_header):
        create_user(username="author")
        create_user(username="rater")
        data = _create_widget(client, auth_header, "author")  # draft
        assert self._rate(client, auth_header("rater"), data["id"], 5).status_code == 404

    def test_rate_requires_auth(self, client):
        assert client.post("/widgets/1/rate", json={"rating": 5}).status_code == 401
