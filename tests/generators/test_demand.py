"""Topics readers want (app/generators/demand.py), through GET /generators/wanted-topics."""

import pytest

from app.generators.demand import THIN_BELOW


@pytest.fixture()
def admin_header(create_user, auth_header):
    create_user(username="admin", is_admin=True)
    return auth_header("admin")


@pytest.fixture()
def reader(create_user, db_session):
    def _make(name, follows=(), preferred=(), banned=False):
        user = create_user(username=name)
        user.bubble_settings = {"custom_topics": list(follows)}
        user.algo_settings = {"preferred_categories": list(preferred)}
        user.is_banned = banned
        db_session.commit()

    return _make


def _wanted(client, headers):
    res = client.get("/generators/wanted-topics", headers=headers)
    assert res.status_code == 200
    return res.json()["topics"]


def test_most_followed_first_with_their_recent_posts(
    client, admin_header, reader, create_user, create_post
):
    reader("a", follows=["Chess", "go"], preferred=["chess"])  # chess twice counts once
    reader("b", follows=["chess"])
    reader("c", preferred=["#Go"])
    reader("d", follows=["chess"], banned=True)
    author = create_user(username="author")
    for _ in range(THIN_BELOW):
        create_post(author, text="#chess")
    create_post(author, text="#go")

    # Tied on readers: the thinner topic first.
    assert _wanted(client, admin_header) == [
        {"topic": "go", "readers": 2, "posts": 1, "thin": True},
        {"topic": "chess", "readers": 2, "posts": THIN_BELOW, "thin": False},
    ]


def test_nobody_follows_anything(client, admin_header):
    assert _wanted(client, admin_header) == []


def test_only_admins_see_it(client, create_user, auth_header):
    create_user(username="someone")
    assert (
        client.get("/generators/wanted-topics", headers=auth_header("someone")).status_code == 403
    )
