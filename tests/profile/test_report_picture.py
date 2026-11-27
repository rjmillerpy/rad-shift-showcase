"""Reporting someone's profile picture (POST /profile/{username}/report-picture)."""

import pytest

from app.admin.models import Report


@pytest.fixture()
def owner(create_user, db_session):
    user = create_user(username="owner")
    user.profile_picture_url = "https://test-bucket.s3.amazonaws.com/profile/owner.jpg"
    db_session.commit()
    return user


@pytest.fixture()
def reader(create_user, auth_header):
    create_user(username="reader")
    return auth_header("reader")


def _report(client, username, headers, reason="offensive"):
    return client.post(
        f"/profile/{username}/report-picture", json={"reason": reason}, headers=headers
    )


def test_a_report_names_the_pictures_owner(client, owner, reader, db_session):
    resp = _report(client, "owner", reader)

    assert resp.json() == {"status": "created", "username": "owner"}
    (report,) = db_session.query(Report).all()
    assert (report.target_type, report.reported_user_id, report.post_id) == (
        "profile_picture",
        owner.id,
        None,
    )


def test_not_your_own(client, owner, auth_header):
    assert _report(client, "owner", auth_header("owner")).status_code == 400


def test_someone_without_a_picture(client, create_user, reader):
    create_user(username="plain")
    assert _report(client, "plain", reader).status_code == 404


def test_an_unknown_user(client, reader):
    assert _report(client, "nobody", reader).status_code == 404


def test_signed_in_only(client, owner):
    assert _report(client, "owner", {}).status_code == 401
