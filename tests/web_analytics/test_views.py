"""Page views through POST /analytics/page-views, and engagements recorded by the real toggles."""

import json

import pytest

from app.web_analytics.models import AnalyticsEvent

BROWSER = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0"}


def _beacon(client, body, headers=BROWSER):
    # What navigator.sendBeacon sends: a JSON string as text/plain.
    return client.post(
        "/analytics/page-views", content=body, headers={**headers, "content-type": "text/plain"}
    )


class TestPageViews:
    def test_a_beacon_records_its_pages(self, client, db_session):
        resp = _beacon(client, json.dumps({"paths": ["/ledger", "/post/42?x=1"]}))
        assert resp.json() == {"accepted": 2}
        rows = [
            (e.path, e.mode) for e in db_session.query(AnalyticsEvent).order_by(AnalyticsEvent.id)
        ]
        assert rows == [("/ledger", "ledger"), ("/post/:id", "post")]

    def test_no_account_is_attached_even_when_signed_in(
        self, client, db_session, create_user, auth_header
    ):
        create_user(username="reader")
        _beacon(client, json.dumps({"paths": ["/agora"]}), {**BROWSER, **auth_header("reader")})
        (event,) = db_session.query(AnalyticsEvent).all()
        assert "reader" not in json.dumps(
            {c: str(getattr(event, c)) for c in ("visitor", "path", "mode")}
        )

    @pytest.mark.parametrize(
        "body", ["not json", '{"paths": []}', '{"pages": ["/"]}', json.dumps({"paths": ["/"] * 26})]
    )
    def test_bad_batches_are_refused(self, client, body):
        assert _beacon(client, body).status_code == 422

    def test_an_oversized_body_is_refused(self, client):
        assert _beacon(client, "x" * 20_000).status_code == 413

    def test_bots_are_accepted_but_not_counted(self, client, db_session):
        resp = _beacon(client, json.dumps({"paths": ["/"]}), {"user-agent": "Googlebot/2.1"})
        assert resp.json() == {"accepted": 0}


class TestEngagements:
    @pytest.fixture()
    def post(self, create_user, create_post):
        return create_post(create_user(username="author"))

    @pytest.fixture()
    def reader(self, create_user, auth_header):
        create_user(username="reader")
        return {**BROWSER, **auth_header("reader")}

    def _engagements(self, db_session):
        return [
            (e.action, e.mode, e.source, e.post_id)
            for e in db_session.query(AnalyticsEvent)
            .filter_by(event_type="engagement")
            .order_by(AnalyticsEvent.id)
        ]

    @pytest.mark.parametrize(
        ("route", "action"),
        [
            ("like", "like"),
            ("laugh", "laugh"),
            ("repost", "repost"),
            ("save", "save"),
            ("share", "share"),
        ],
    )
    def test_each_engagement_is_recorded_with_its_feed_mode(
        self, client, db_session, post, reader, route, action
    ):
        client.post(f"/posts/{route}/{post.id}", headers={**reader, "x-feed-mode": "ledger"})
        assert self._engagements(db_session) == [(action, "ledger", "user", post.id)]

    def test_undoing_isnt_engagement(self, client, db_session, post, reader):
        client.post(f"/posts/like/{post.id}", headers=reader)
        client.post(f"/posts/like/{post.id}", headers=reader)  # unlike
        assert [a for a, *_ in self._engagements(db_session)] == ["like"]

    def test_an_unknown_mode_is_recorded_as_none(self, client, db_session, post, reader):
        client.post(f"/posts/like/{post.id}", headers={**reader, "x-feed-mode": "<script>"})
        assert self._engagements(db_session)[0][1] is None

    def test_a_scraped_posts_source(self, client, db_session, post, reader):
        post.post_metadata = '{"source": {"platform": "rss"}}'
        db_session.commit()
        client.post(f"/posts/like/{post.id}", headers={**reader, "x-feed-mode": "agora"})
        assert self._engagements(db_session)[0][2] == "scraped"
