"""The widget store's like, save, review and report endpoints (product roadmap Phase 1).

Known bug: the store pages called these and none existed; liking, saving,
reviewing and reporting all failed silently.
"""

import pytest

from app.widgets.constants import WIDGET_REPORTS_FOR_REVIEW
from app.widgets.models import Widget
from tests.widgets._view_helpers import _make_approved_widget


@pytest.fixture()
def widget_id(client, auth_header, create_user, db_session):
    return _make_approved_widget(client, auth_header, create_user, db_session)["id"]


@pytest.fixture()
def fan(create_user, auth_header):
    create_user(username="fan")
    return auth_header("fan")


class TestLikeAndSave:
    @pytest.mark.parametrize(
        ("action", "flag", "count"), [("like", "liked", "likes"), ("save", "saved", "saves")]
    )
    def test_on_twice_counts_once_and_off_undoes_it(
        self, client, widget_id, fan, action, flag, count
    ):
        client.post(f"/widgets/{widget_id}/{action}", headers=fan)
        on = client.post(f"/widgets/{widget_id}/{action}", headers=fan).json()
        off = client.delete(f"/widgets/{widget_id}/{action}", headers=fan).json()

        assert (on[flag], on[count]) == (True, 1)
        assert (off[flag], off[count]) == (False, 0)

    @pytest.mark.parametrize("action", ["like", "save"])
    def test_needs_a_login(self, client, widget_id, action):
        assert client.post(f"/widgets/{widget_id}/{action}").status_code == 401


class TestDetailShowsTheViewer:
    def test_anonymous_sees_everything_off(self, client, widget_id):
        body = client.get(f"/widgets/{widget_id}").json()
        assert (body["installed"], body["liked"], body["saved"], body["my_rating"]) == (
            False, False, False, None,
        )  # fmt: skip

    def test_a_logged_in_viewer_sees_their_own_state(self, client, widget_id, fan):
        for action in ("install", "like", "save"):
            client.post(f"/widgets/{widget_id}/{action}", headers=fan)
        client.post(f"/widgets/{widget_id}/rate", json={"rating": 4}, headers=fan)

        body = client.get(f"/widgets/{widget_id}", headers=fan).json()

        assert (body["installed"], body["liked"], body["saved"], body["my_rating"]) == (
            True, True, True, 4,
        )  # fmt: skip
        assert body["widget"]["rating_avg"] == 4.0


class TestReviews:
    def test_a_review_is_listed_with_its_author_and_stars(self, client, widget_id, fan):
        posted = client.post(
            f"/widgets/{widget_id}/reviews", json={"text": "Handy", "rating": 5}, headers=fan
        )
        listed = client.get(f"/widgets/{widget_id}/reviews").json()["reviews"]

        assert posted.status_code == 200
        assert [(r["username"], r["rating"], r["text"]) for r in listed] == [("fan", 5, "Handy")]

    def test_stars_from_an_earlier_rating_are_reused(self, client, widget_id, fan):
        client.post(f"/widgets/{widget_id}/rate", json={"rating": 2}, headers=fan)
        posted = client.post(f"/widgets/{widget_id}/reviews", json={"text": "Meh"}, headers=fan)
        assert posted.json()["review"]["rating"] == 2

    def test_a_review_needs_stars(self, client, widget_id, fan):
        resp = client.post(f"/widgets/{widget_id}/reviews", json={"text": "No stars"}, headers=fan)
        assert resp.status_code == 400

    def test_stars_only_ratings_are_not_listed_as_reviews(self, client, widget_id, fan):
        client.post(f"/widgets/{widget_id}/rate", json={"rating": 5}, headers=fan)
        assert client.get(f"/widgets/{widget_id}/reviews").json()["reviews"] == []


class TestReport:
    def test_enough_reports_send_the_widget_back_to_review(
        self, client, widget_id, create_user, auth_header, db_session
    ):
        responses = []
        for i in range(WIDGET_REPORTS_FOR_REVIEW):
            create_user(username=f"reporter{i}")
            responses.append(
                client.post(
                    f"/widgets/{widget_id}/report",
                    json={"reason": "steals data"},
                    headers=auth_header(f"reporter{i}"),
                ).json()
            )

        widget = db_session.get(Widget, widget_id)
        assert [r["under_review"] for r in responses] == [False] * (
            WIDGET_REPORTS_FOR_REVIEW - 1
        ) + [True]
        assert widget.status == "pending"
        assert client.get("/widgets").json()["widgets"] == [], "out of the store while under review"

    def test_one_user_reporting_again_counts_once(self, client, widget_id, fan, db_session):
        for _ in range(WIDGET_REPORTS_FOR_REVIEW):
            resp = client.post(f"/widgets/{widget_id}/report", json={"reason": "bad"}, headers=fan)
        assert resp.json()["status"] == "updated"
        assert db_session.get(Widget, widget_id).status == "approved"

    def test_the_author_cannot_report_their_own(self, client, widget_id, auth_header):
        resp = client.post(
            f"/widgets/{widget_id}/report", json={"reason": "bad"}, headers=auth_header("author")
        )
        assert resp.status_code == 400
