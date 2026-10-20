"""Shared helpers for widget API view tests."""

import time

from app.widgets.models import Widget

VALID_WIDGET = {
    "title": "Test Widget",
    "description": "A test widget",
    "category": "tool",
    "language": "html",
    "code": "<div>Hello</div>",
    "css": "body { color: red; }",
    "default_width": 400,
    "default_height": 300,
    "resizable": False,
}


def _create_widget(client, auth_header, username, **overrides):
    """Create a widget via the API and return the JSON response body."""
    payload = {**VALID_WIDGET, **overrides}
    resp = client.post(
        "/widgets/create",
        json=payload,
        headers=auth_header(username),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_approved_widget(client, auth_header, create_user, db_session, username="author"):
    """Create a widget and force it to approved status directly in the DB."""
    create_user(username=username)
    data = _create_widget(client, auth_header, username)
    widget_id = data["id"]
    w = db_session.query(Widget).filter(Widget.id == widget_id).first()
    w.status = "approved"
    w.published_at = int(time.time())
    db_session.commit()
    db_session.refresh(w)
    return data
