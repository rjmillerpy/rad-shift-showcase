"""Bans are enforced (known bug: is_banned was set by admins and checked nowhere).

A banned user keeps a valid token until it expires; every authenticated
route family must refuse it, and their posts must vanish from public reads.
"""

import pytest

from app.common.constants import ACCOUNT_SUSPENDED_DETAIL

# (method, path, a valid body): the ban check must answer, not validation.
AUTHENTICATED_ROUTES = [
    ("GET", "/posts/saved", None),  # app.common.deps.required_user
    ("POST", "/blog/create", {"title": "T", "content_html": "<p>x</p>"}),  # blog._require_user
    ("GET", "/widgets/my", None),  # app.widgets.views._require_user
    ("POST", "/follow/someone", {}),  # app.follow.views
    ("POST", "/avatar/regenerate", None),  # app.avatar.views
]


@pytest.fixture()
def banned_author(create_user, create_post, db_session):
    user = create_user(username="banned")
    create_post(user=user, text="banned author's post")
    create_user(username="someone")
    user.is_banned = True
    db_session.commit()
    return user


@pytest.mark.parametrize(("method", "path", "body"), AUTHENTICATED_ROUTES)
def test_every_authenticated_route_refuses_a_banned_token(
    client, banned_author, auth_header, method, path, body
):
    resp = client.request(method, path, headers=auth_header("banned"), json=body)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ACCOUNT_SUSPENDED_DETAIL


def test_their_posts_vanish_from_feeds_search_and_links(client, banned_author):
    (post,) = banned_author.posts

    assert client.get("/posts/").json()["posts"] == []
    assert client.get("/posts/search/posts", params={"q": "banned"}).json()["posts"] == []
    assert client.get(f"/posts/{post.id}").status_code == 404
