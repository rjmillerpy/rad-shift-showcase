"""Reporting a blog post (POST /blog/{id}/report) into the moderators' queue."""

import pytest

from app.admin.models import Report


@pytest.fixture()
def blog_id(client, create_user, auth_header):
    create_user("blogger")
    resp = client.post("/blog/create", json={"title": "Miracle cure", "content_html": "<p>x</p>",
                                             "is_draft": False}, headers=auth_header("blogger"))  # fmt: skip
    return resp.json()["blog_post"]["id"]


@pytest.fixture()
def reader(create_user, auth_header):
    create_user("reader")
    return auth_header("reader")


def _report(client, blog_id, headers, reason="medical misinformation"):
    return client.post(f"/blog/{blog_id}/report", json={"reason": reason}, headers=headers)


def test_a_report_is_filed_once_and_updated_after(client, blog_id, reader, db_session):
    first = _report(client, blog_id, reader)
    second = _report(client, blog_id, reader, reason="scam")

    assert (first.json()["status"], second.json()["status"]) == ("created", "updated")
    (report,) = db_session.query(Report).all()
    assert (report.target_type, report.blog_id, report.post_id, report.reason) == (
        "blog",
        blog_id,
        None,
        "scam",
    )


def test_not_your_own(client, blog_id, auth_header):
    assert _report(client, blog_id, auth_header("blogger")).status_code == 400


def test_not_a_draft(client, create_user, auth_header, reader):
    create_user("drafter")
    draft = client.post("/blog/create", json={"title": "WIP", "content_html": "<p>x</p>"},
                        headers=auth_header("drafter")).json()["blog_post"]  # fmt: skip
    assert _report(client, draft["id"], reader).status_code == 404


def test_signed_in_only(client, blog_id):
    assert _report(client, blog_id, {}).status_code == 401


def test_a_reason_is_required(client, blog_id, reader):
    assert _report(client, blog_id, reader, reason="").status_code == 422
