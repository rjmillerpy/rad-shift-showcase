"""Content warnings on posts (product roadmap Phase 2): set by the author."""

import pytest


def _post(client, headers, **form):
    return client.post(
        "/posts/add", data={"text": "the ending of the film", **form}, headers=headers
    )


def test_the_author_sets_one_and_every_reader_gets_it(client, create_user, auth_header):
    create_user(username="author")
    assert _post(client, auth_header("author"), content_warning=" spoilers ").status_code == 200

    (post,) = client.get("/posts/").json()["posts"]

    assert post["content_warning"] == "spoilers"


@pytest.mark.parametrize("form", [{}, {"content_warning": "   "}], ids=["absent", "blank"])
def test_no_warning_is_null(client, create_user, auth_header, form):
    create_user(username="author")
    _post(client, auth_header("author"), **form)
    assert client.get("/posts/").json()["posts"][0]["content_warning"] is None


def test_a_warning_is_a_short_label(client, create_user, auth_header):
    create_user(username="author")
    assert _post(client, auth_header("author"), content_warning="x" * 101).status_code == 422
