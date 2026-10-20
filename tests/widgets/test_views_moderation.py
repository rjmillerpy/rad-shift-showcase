"""API endpoint tests for widget submission, admin review, and pending list."""

from app.widgets.models import Widget
from tests.widgets._view_helpers import _create_widget


class TestWidgetSubmission:
    def test_submit_for_review(self, client, create_user, auth_header):
        create_user(username="author")
        data = _create_widget(client, auth_header, "author")
        resp = client.post(
            "/widgets/submit",
            json={"widget_id": data["id"]},
            headers=auth_header("author"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["security_score"] is not None
        assert body["scan_passed"] is True

    def test_submit_runs_security_scan(self, client, create_user, auth_header):
        create_user(username="author")
        data = _create_widget(client, auth_header, "author")
        resp = client.post(
            "/widgets/submit",
            json={"widget_id": data["id"]},
            headers=auth_header("author"),
        )
        body = resp.json()
        assert body["security_score"] is not None
        assert body["scan_passed"] is not None
        # Clean code should pass with high score
        assert body["security_score"] >= 60

    def test_submit_malicious_code_fails_scan(self, client, create_user, auth_header):
        create_user(username="author")
        data = _create_widget(
            client,
            auth_header,
            "author",
            code="eval('alert(1)')",
        )
        resp = client.post(
            "/widgets/submit",
            json={"widget_id": data["id"]},
            headers=auth_header("author"),
        )
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["scan_passed"] is False
        assert body["security_score"] == 0
        assert "security scan failed" in body["review_notes"].lower()

    def test_cannot_submit_already_submitted(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        data = _create_widget(client, auth_header, "author")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "submitted"
        db_session.commit()
        resp = client.post(
            "/widgets/submit",
            json={"widget_id": data["id"]},
            headers=auth_header("author"),
        )
        assert resp.status_code == 400
        assert "Cannot submit" in resp.json()["detail"]

    def test_cannot_submit_approved_widget(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        data = _create_widget(client, auth_header, "author")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "approved"
        db_session.commit()
        resp = client.post(
            "/widgets/submit",
            json={"widget_id": data["id"]},
            headers=auth_header("author"),
        )
        assert resp.status_code == 400

    def test_cannot_submit_others_widget(self, client, create_user, auth_header):
        create_user(username="owner")
        create_user(username="other")
        data = _create_widget(client, auth_header, "owner")
        resp = client.post(
            "/widgets/submit",
            json={"widget_id": data["id"]},
            headers=auth_header("other"),
        )
        assert resp.status_code == 404

    def test_submit_requires_auth(self, client):
        resp = client.post("/widgets/submit", json={"widget_id": 1})
        assert resp.status_code == 401


class TestWidgetReview:
    def test_admin_approve(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        admin = create_user(username="admin", is_admin=True)
        data = _create_widget(client, auth_header, "author")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "submitted"
        db_session.commit()

        resp = client.post(
            "/widgets/review",
            json={"widget_id": data["id"], "action": "approve", "notes": "Looks good"},
            headers=auth_header("admin"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["review_notes"] == "Looks good"
        assert body["reviewed_by"] == admin.id
        assert body["published_at"] is not None

    def test_admin_reject(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        create_user(username="admin", is_admin=True)
        data = _create_widget(client, auth_header, "author")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "submitted"
        db_session.commit()

        resp = client.post(
            "/widgets/review",
            json={"widget_id": data["id"], "action": "reject", "notes": "Not acceptable"},
            headers=auth_header("admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_admin_suspend(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        create_user(username="admin", is_admin=True)
        data = _create_widget(client, auth_header, "author")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "approved"
        db_session.commit()

        resp = client.post(
            "/widgets/review",
            json={"widget_id": data["id"], "action": "suspend", "notes": "Policy violation"},
            headers=auth_header("admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

    def test_cannot_approve_non_submitted_widget(self, client, create_user, auth_header):
        create_user(username="author")
        create_user(username="admin", is_admin=True)
        data = _create_widget(client, auth_header, "author")  # status=draft

        resp = client.post(
            "/widgets/review",
            json={"widget_id": data["id"], "action": "approve"},
            headers=auth_header("admin"),
        )
        assert resp.status_code == 400
        assert "Cannot approve" in resp.json()["detail"]

    def test_non_admin_cannot_review(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        create_user(username="regular")
        data = _create_widget(client, auth_header, "author")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "submitted"
        db_session.commit()

        resp = client.post(
            "/widgets/review",
            json={"widget_id": data["id"], "action": "approve"},
            headers=auth_header("regular"),
        )
        assert resp.status_code == 403

    def test_invalid_review_action(self, client, create_user, auth_header):
        create_user(username="admin", is_admin=True)
        resp = client.post(
            "/widgets/review",
            json={"widget_id": 1, "action": "ban"},
            headers=auth_header("admin"),
        )
        assert resp.status_code == 422  # Pydantic regex validation

    def test_pending_list(self, client, create_user, auth_header, db_session):
        create_user(username="author")
        create_user(username="admin", is_admin=True)
        data = _create_widget(client, auth_header, "author", title="Pending Widget")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "submitted"
        db_session.commit()

        resp = client.get("/widgets/pending", headers=auth_header("admin"))
        assert resp.status_code == 200
        titles = [w["title"] for w in resp.json()["widgets"]]
        assert "Pending Widget" in titles

    def test_pending_list_non_admin_forbidden(self, client, create_user, auth_header):
        create_user(username="regular")
        resp = client.get("/widgets/pending", headers=auth_header("regular"))
        assert resp.status_code == 403

    def test_review_requires_auth(self, client):
        resp = client.post("/widgets/review", json={"widget_id": 1, "action": "approve"})
        assert resp.status_code == 401


class TestPendingWidgetsEndpoint:
    def test_pending_requires_admin(self, client, auth_header, create_user):
        create_user(username="plain")
        resp = client.get("/widgets/pending", headers=auth_header("plain"))
        assert resp.status_code == 403

    def test_pending_returns_submitted_widgets_for_admin(
        self,
        client,
        auth_header,
        create_user,
        db_session,
    ):
        create_user(username="adm", is_admin=True)
        create_user(username="auth")
        data = _create_widget(client, auth_header, "auth")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.status = "submitted"
        db_session.commit()

        resp = client.get("/widgets/pending", headers=auth_header("adm"))
        assert resp.status_code == 200
        assert any(widget["id"] == data["id"] for widget in resp.json()["widgets"])
