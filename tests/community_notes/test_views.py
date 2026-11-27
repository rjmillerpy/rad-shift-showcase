"""Tests for app/community_notes/views.py through the real app.

TestClient runs background tasks before returning, so a rating's rescore
has happened by the time the next request looks.
"""

import pytest

from app.community_notes.constants import MIN_RATINGS, NoteStatus

NOTE = {"text": "The photo is from 2019, not this week.", "source_url": "https://example.com/a"}


@pytest.fixture()
def post_by_author(create_user, create_post):
    return create_post(create_user(username="author"), text="Flooding downtown right now")


@pytest.fixture()
def writer(create_user, auth_header):
    create_user(username="writer")
    return auth_header("writer")


def _write(client, headers, post_id, body=NOTE):
    return client.post(f"/notes/posts/{post_id}", json=body, headers=headers)


def _raters(create_user, auth_header, count):
    return [create_user(username=f"rater{i}") and auth_header(f"rater{i}") for i in range(count)]


class TestWriting:
    def test_a_note_starts_waiting_for_ratings(self, client, writer, post_by_author):
        response = _write(client, writer, post_by_author.id)
        assert response.status_code == 200
        note = response.json()
        assert (note["status"], note["is_mine"], note["my_rating"]) == (
            NoteStatus.NEEDS_MORE_RATINGS,
            True,
            None,
        )
        assert note["source_url"] == "https://example.com/a"

    def test_not_on_your_own_post(self, client, auth_header, post_by_author):
        assert _write(client, auth_header("author"), post_by_author.id).status_code == 400

    @pytest.mark.parametrize("draft", [True])
    def test_not_on_a_draft(self, client, writer, create_post, create_user, draft):
        draft_post = create_post(create_user(username="drafter"), is_draft=draft)
        assert _write(client, writer, draft_post.id).status_code == 404

    def test_not_on_a_missing_post(self, client, writer):
        assert _write(client, writer, 999).status_code == 404

    def test_signed_in_only(self, client, post_by_author):
        assert client.post(f"/notes/posts/{post_by_author.id}", json=NOTE).status_code == 401

    @pytest.mark.parametrize(
        "body",
        [
            {"text": ""},
            {"text": "x" * 501},
            {"text": "fine", "source_url": "javascript:alert(1)"},
            {"text": "fine", "source_url": "ftp://example.com/file"},
        ],
        ids=["empty", "too-long", "javascript-url", "not-http"],
    )
    def test_bad_notes_are_rejected(self, client, writer, post_by_author, body):
        assert _write(client, writer, post_by_author.id, body).status_code == 422

    def test_writing_again_replaces_your_note_and_its_ratings(
        self, client, writer, post_by_author, create_user, auth_header
    ):
        first = _write(client, writer, post_by_author.id).json()
        (rater,) = _raters(create_user, auth_header, 1)
        client.post(f"/notes/{first['id']}/rating", json={"helpful": True}, headers=rater)

        second = _write(client, writer, post_by_author.id, {"text": "Reworded."}).json()

        assert second["id"] == first["id"]
        notes = client.get(f"/notes/posts/{post_by_author.id}", headers=rater).json()["notes"]
        assert [(n["text"], n["my_rating"]) for n in notes] == [("Reworded.", None)]


class TestRating:
    def test_not_your_own_note(self, client, writer, post_by_author):
        note = _write(client, writer, post_by_author.id).json()
        response = client.post(
            f"/notes/{note['id']}/rating", json={"helpful": True}, headers=writer
        )
        assert response.status_code == 400

    def test_rating_again_changes_your_rating(
        self, client, writer, post_by_author, create_user, auth_header
    ):
        note = _write(client, writer, post_by_author.id).json()
        (rater,) = _raters(create_user, auth_header, 1)
        for helpful in (True, False):
            client.post(f"/notes/{note['id']}/rating", json={"helpful": helpful}, headers=rater)
        notes = client.get(f"/notes/posts/{post_by_author.id}", headers=rater).json()["notes"]
        assert notes[0]["my_rating"] is False

    def test_a_missing_note(self, client, writer):
        assert (
            client.post("/notes/999/rating", json={"helpful": True}, headers=writer).status_code
            == 404
        )


class TestShowing:
    def test_a_note_rated_helpful_by_enough_people_appears_on_the_post(
        self, client, writer, post_by_author, create_user, auth_header
    ):
        note = _write(client, writer, post_by_author.id).json()
        for rater in _raters(create_user, auth_header, MIN_RATINGS + 3):
            client.post(f"/notes/{note['id']}/rating", json={"helpful": True}, headers=rater)

        (post,) = client.get("/posts/").json()["posts"]

        assert post["community_note"] == {
            "id": note["id"],
            "text": NOTE["text"],
            "source_url": NOTE["source_url"],
        }

    def test_a_new_note_is_not_shown(self, client, writer, post_by_author):
        _write(client, writer, post_by_author.id)
        assert client.get("/posts/").json()["posts"][0]["community_note"] is None


class TestRatingQueue:
    def test_lists_notes_you_can_still_rate(
        self, client, writer, post_by_author, create_user, auth_header
    ):
        note = _write(client, writer, post_by_author.id).json()
        (rater,) = _raters(create_user, auth_header, 1)

        before = client.get("/notes/needs-ratings", headers=rater).json()["notes"]
        client.post(f"/notes/{note['id']}/rating", json={"helpful": True}, headers=rater)
        after = client.get("/notes/needs-ratings", headers=rater).json()["notes"]

        assert [n["id"] for n in before] == [note["id"]]
        assert after == []

    def test_never_your_own_notes(self, client, writer, post_by_author):
        _write(client, writer, post_by_author.id)
        assert client.get("/notes/needs-ratings", headers=writer).json()["notes"] == []
