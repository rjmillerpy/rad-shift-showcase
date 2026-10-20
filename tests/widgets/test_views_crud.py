"""API endpoint tests for widget create / read / update / delete."""

import time

import pytest

from app.widgets.models import Widget, WidgetInstall, WidgetReview
from tests.widgets._view_helpers import VALID_WIDGET, _create_widget


class TestWidgetCreate:
    def test_create_widget(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post(
            "/widgets/create",
            json=VALID_WIDGET,
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Test Widget"
        assert body["status"] == "draft"
        assert body["author_username"] == "alice"
        assert body["version"] == "1.0.0"
        assert body["install_count"] == 0
        assert body["id"] is not None

    def test_create_from_template(self, client, create_user, auth_header, db_session):
        from app.widgets.models import WidgetTemplate

        tpl = WidgetTemplate(
            name="Test Tpl",
            category="game",
            language="html",
            description="tpl",
            starter_code="<p>tpl</p>",
            icon_emoji="X",
        )
        db_session.add(tpl)
        db_session.commit()
        db_session.refresh(tpl)

        create_user(username="bob")
        resp = client.post(
            "/widgets/create",
            json={**VALID_WIDGET, "template_id": tpl.id, "icon_emoji": None},
            headers=auth_header("bob"),
        )
        assert resp.status_code == 200
        # icon_emoji should be inherited from the template when not provided
        assert resp.json()["icon_emoji"] == "X"

    def test_create_requires_auth(self, client):
        resp = client.post("/widgets/create", json=VALID_WIDGET)
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        "field,value,expected_status",
        [
            ("title", "", 422),  # min_length=1
            ("category", "invalid", 422),  # regex validation
            ("language", "brainfuck", 422),  # regex validation
            ("default_width", 50, 422),  # ge=200
            ("default_width", 9999, 422),  # le=1200
            ("default_height", 50, 422),  # ge=200
            ("default_height", 9999, 422),  # le=800
        ],
        ids=[
            "empty-title",
            "bad-category",
            "bad-language",
            "width-too-small",
            "width-too-large",
            "height-too-small",
            "height-too-large",
        ],
    )
    def test_create_validation(
        self, client, create_user, auth_header, field, value, expected_status
    ):
        create_user(username="val_user")
        payload = {**VALID_WIDGET, field: value}
        resp = client.post(
            "/widgets/create",
            json=payload,
            headers=auth_header("val_user"),
        )
        assert resp.status_code == expected_status

    def test_create_with_all_optional_fields(self, client, create_user, auth_header):
        create_user(username="full")
        payload = {
            **VALID_WIDGET,
            "icon_emoji": "R",
            "tags": ["test", "cool"],
            "permissions": ["clipboard"],
            "config": {"key": "value"},
            "default_width": 600,
            "default_height": 500,
            "resizable": True,
        }
        resp = client.post(
            "/widgets/create",
            json=payload,
            headers=auth_header("full"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["icon_emoji"] == "R"
        assert body["tags"] == ["test", "cool"]
        assert body["permissions"] == ["clipboard"]
        assert body["resizable"] is True
        assert body["default_width"] == 600

    def test_create_sets_timestamps(self, client, create_user, auth_header):
        create_user(username="ts_user")
        before = int(time.time())
        resp = client.post(
            "/widgets/create",
            json=VALID_WIDGET,
            headers=auth_header("ts_user"),
        )
        after = int(time.time())
        body = resp.json()
        assert before <= body["created_at"] <= after


class TestWidgetCRUD:
    def test_get_widget(self, client, create_user, auth_header):
        create_user(username="owner")
        data = _create_widget(client, auth_header, "owner")
        resp = client.get(f"/widgets/{data['id']}")
        assert resp.status_code == 200
        assert resp.json()["widget"]["id"] == data["id"]

    def test_get_nonexistent_widget(self, client):
        resp = client.get("/widgets/99999")
        assert resp.status_code == 404

    def test_update_own_widget(self, client, create_user, auth_header):
        create_user(username="owner")
        data = _create_widget(client, auth_header, "owner")
        resp = client.put(
            f"/widgets/{data['id']}",
            json={"title": "Updated Title", "code": "<p>Updated</p>"},
            headers=auth_header("owner"),
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"
        assert resp.json()["code"] == "<p>Updated</p>"

    def test_cannot_update_others_widget(self, client, create_user, auth_header):
        create_user(username="owner")
        create_user(username="intruder")
        data = _create_widget(client, auth_header, "owner")
        resp = client.put(
            f"/widgets/{data['id']}",
            json={"title": "Hacked"},
            headers=auth_header("intruder"),
        )
        assert resp.status_code == 404

    def test_cannot_update_submitted_widget(self, client, create_user, auth_header, db_session):
        create_user(username="owner")
        data = _create_widget(client, auth_header, "owner")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "submitted"
        db_session.commit()
        resp = client.put(
            f"/widgets/{data['id']}",
            json={"title": "Edit"},
            headers=auth_header("owner"),
        )
        assert resp.status_code == 400
        assert "Cannot edit" in resp.json()["detail"]

    def test_update_rejected_widget_resets_to_draft(
        self, client, create_user, auth_header, db_session
    ):
        create_user(username="owner")
        data = _create_widget(client, auth_header, "owner")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "rejected"
        w.review_notes = "Bad code"
        w.security_score = 10
        db_session.commit()
        resp = client.put(
            f"/widgets/{data['id']}",
            json={"title": "Fixed"},
            headers=auth_header("owner"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "draft"
        assert body["review_notes"] is None
        assert body["security_score"] is None

    def test_delete_widget(self, client, create_user, auth_header):
        create_user(username="owner")
        data = _create_widget(client, auth_header, "owner")
        resp = client.delete(
            f"/widgets/{data['id']}",
            headers=auth_header("owner"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        # Verify it's gone
        resp2 = client.get(f"/widgets/{data['id']}")
        assert resp2.status_code == 404

    def test_cannot_delete_others_widget(self, client, create_user, auth_header):
        create_user(username="owner")
        create_user(username="other")
        data = _create_widget(client, auth_header, "owner")
        resp = client.delete(
            f"/widgets/{data['id']}",
            headers=auth_header("other"),
        )
        assert resp.status_code == 404

    def test_delete_cleans_up_installs_and_reviews(
        self, client, create_user, auth_header, db_session
    ):
        create_user(username="owner")
        data = _create_widget(client, auth_header, "owner")
        wid = data["id"]
        # Add install and review rows directly
        db_session.add(WidgetInstall(user_id=1, widget_id=wid, installed_at=int(time.time())))
        db_session.add(
            WidgetReview(user_id=1, widget_id=wid, rating=5, created_at=int(time.time()))
        )
        db_session.commit()

        resp = client.delete(f"/widgets/{wid}", headers=auth_header("owner"))
        assert resp.status_code == 200
        assert db_session.query(WidgetInstall).filter(WidgetInstall.widget_id == wid).count() == 0
        assert db_session.query(WidgetReview).filter(WidgetReview.widget_id == wid).count() == 0

    def test_list_my_widgets(self, client, create_user, auth_header):
        create_user(username="owner")
        _create_widget(client, auth_header, "owner", title="W1")
        _create_widget(client, auth_header, "owner", title="W2")
        resp = client.get("/widgets/my", headers=auth_header("owner"))
        assert resp.status_code == 200
        titles = [w["title"] for w in resp.json()["widgets"]]
        assert "W1" in titles
        assert "W2" in titles

    def test_list_my_widgets_excludes_others(self, client, create_user, auth_header):
        create_user(username="alice")
        create_user(username="bob")
        _create_widget(client, auth_header, "alice", title="Alice's")
        _create_widget(client, auth_header, "bob", title="Bob's")
        resp = client.get("/widgets/my", headers=auth_header("alice"))
        titles = [w["title"] for w in resp.json()["widgets"]]
        assert "Alice's" in titles
        assert "Bob's" not in titles

    def test_list_my_widgets_requires_auth(self, client):
        resp = client.get("/widgets/my")
        assert resp.status_code == 401
