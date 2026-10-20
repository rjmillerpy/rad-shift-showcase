"""API endpoint tests for widget browsing, rendering, and templates."""

import pytest

from app.widgets.models import Widget
from tests.widgets._view_helpers import _create_widget, _make_approved_widget


class TestWidgetBrowse:
    def test_browse_approved_only(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        _create_widget(client, auth_header, "author", title="Draft")
        approved = _create_widget(client, auth_header, "author", title="Approved")
        w = db_session.query(Widget).filter(Widget.id == approved["id"]).first()
        w.status = "approved"
        db_session.commit()

        resp = client.get("/widgets/browse")
        assert resp.status_code == 200
        titles = [w["title"] for w in resp.json()["widgets"]]
        assert "Approved" in titles
        assert "Draft" not in titles

    @pytest.mark.parametrize(
        "category",
        [
            "game",
            "tool",
            "api_connector",
            "display_modifier",
            "lambda",
            "visualization",
            "social",
        ],
    )
    def test_browse_by_category(self, client, create_user, auth_header, db_session, category):
        create_user(username="author")
        data = _create_widget(client, auth_header, "author", category=category)
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "approved"
        db_session.commit()

        resp = client.get(f"/widgets/browse?category={category}")
        assert resp.status_code == 200
        widgets = resp.json()["widgets"]
        assert len(widgets) >= 1
        assert all(w["category"] == category for w in widgets)

    def test_browse_invalid_category(self, client):
        resp = client.get("/widgets/browse?category=invalid")
        assert resp.status_code == 400

    def test_browse_pagination(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        for i in range(5):
            data = _create_widget(client, auth_header, "author", title=f"W{i}")
            w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
            w.status = "approved"
        db_session.commit()

        # First page
        resp = client.get("/widgets/browse?limit=3&offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["widgets"]) == 3
        assert body["has_more"] is True

        # Second page
        resp2 = client.get("/widgets/browse?limit=3&offset=3")
        body2 = resp2.json()
        assert len(body2["widgets"]) == 2
        assert body2["has_more"] is False

    def test_browse_no_auth_required(self, client):
        resp = client.get("/widgets/browse")
        assert resp.status_code == 200

    def test_browse_empty_result(self, client):
        resp = client.get("/widgets/browse")
        assert resp.status_code == 200
        assert resp.json()["widgets"] == []
        assert resp.json()["has_more"] is False


class TestWidgetRender:
    def test_render_approved_widget(self, client, create_user, auth_header, db_session):
        data = _make_approved_widget(
            client, auth_header, create_user, db_session, username="author"
        )
        resp = client.get(f"/widgets/{data['id']}/render")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<div>Hello</div>" in resp.text

    def test_render_includes_css(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        data = _create_widget(
            client,
            auth_header,
            "author",
            code="<p>Styled</p>",
            css="p { color: blue; }",
        )
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "approved"
        db_session.commit()

        resp = client.get(f"/widgets/{data['id']}/render")
        assert resp.status_code == 200
        assert "p { color: blue; }" in resp.text

    def test_render_unapproved_returns_404(self, client, create_user, auth_header):
        create_user(username="author")
        data = _create_widget(client, auth_header, "author")  # draft
        resp = client.get(f"/widgets/{data['id']}/render")
        assert resp.status_code == 404
        assert "not available" in resp.text.lower()

    def test_render_nonexistent_returns_404(self, client):
        resp = client.get("/widgets/99999/render")
        assert resp.status_code == 404

    def test_render_uses_html_output_when_available(
        self, client, create_user, auth_header, db_session
    ):
        create_user(username="author")
        data = _create_widget(client, auth_header, "author")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "approved"
        w.html_output = "<h1>Compiled Output</h1>"
        db_session.commit()

        resp = client.get(f"/widgets/{data['id']}/render")
        assert resp.status_code == 200
        assert "<h1>Compiled Output</h1>" in resp.text


class TestWidgetTemplates:
    def test_list_templates(self, client):
        resp = client.get("/widgets/templates")
        assert resp.status_code == 200
        templates = resp.json()["templates"]
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_templates_have_code(self, client):
        resp = client.get("/widgets/templates")
        templates = resp.json()["templates"]
        for tpl in templates:
            assert "starter_code" in tpl
            assert len(tpl["starter_code"]) > 0

    def test_templates_have_required_fields(self, client):
        resp = client.get("/widgets/templates")
        templates = resp.json()["templates"]
        required = {"name", "category", "language", "description", "starter_code"}
        for tpl in templates:
            assert required.issubset(set(tpl.keys())), (
                f"Missing keys in template: {required - set(tpl.keys())}"
            )

    @pytest.mark.parametrize(
        "category",
        [
            "game",
            "api_connector",
            "lambda",
            "visualization",
            "social",
            "tool",
            "display_modifier",
        ],
    )
    def test_templates_cover_categories(self, client, category):
        resp = client.get("/widgets/templates")
        templates = resp.json()["templates"]
        cats = [t["category"] for t in templates]
        assert category in cats, f"No template for category '{category}'"

    def test_templates_no_auth_required(self, client):
        resp = client.get("/widgets/templates")
        assert resp.status_code == 200
