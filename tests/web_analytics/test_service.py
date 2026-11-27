"""Tests for app/web_analytics/service.py: cleaning, anonymising and recording."""

import pytest

from app.web_analytics.constants import DAY_SECONDS, EVENT_RETENTION_DAYS
from app.web_analytics.models import AnalyticsEvent, VisitorSalt
from app.web_analytics.service import Client, clean_path, content_source, mode_of, record_page_views

READER = Client(ip="203.0.113.7", user_agent="Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0")
DAY = 20_000  # a unix day


@pytest.fixture()
def on_day(monkeypatch):
    def _set(day: int) -> None:
        monkeypatch.setattr(
            "app.web_analytics.service.time.time", lambda: day * DAY_SECONDS + 3600.0
        )

    _set(DAY)
    return _set


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("/ledger", "/ledger"),
        ("/ledger?tab=2#top", "/ledger"),
        ("/post/123", "/post/:id"),
        ("/profile/alice", "/profile/:name"),
        ("/profile/alice/", "/profile/:name"),
        ("/blog/my-first-post", "/blog/:slug"),
        ("/", "/"),
        ("/" + "x" * 500, "/" + "x" * 199),
    ],
)
def test_paths_keep_the_kind_of_page_not_who_or_what(raw, clean):
    assert clean_path(raw) == clean


@pytest.mark.parametrize("raw", ["https://evil.example/x", "//evil.example/x", "ledger", ""])
def test_anything_but_a_local_path_is_dropped(raw):
    assert clean_path(raw) is None


@pytest.mark.parametrize(
    ("path", "mode"),
    [("/ledger", "ledger"), ("/post/:id", "post"), ("/", None), ("/settings", None)],
)
def test_a_path_names_its_feed_mode(path, mode):
    assert mode_of(path) == mode


def test_a_visitor_is_the_same_all_day_and_unlinkable_the_next(db_session, on_day):
    record_page_views(["/ledger", "/agora"], READER, db_session)
    on_day(DAY + 1)
    record_page_views(["/ledger"], READER, db_session)

    first, second, next_day = (
        e.visitor for e in db_session.query(AnalyticsEvent).order_by(AnalyticsEvent.id)
    )
    assert first == second != next_day
    assert READER.ip not in first and len(first) == 16


def test_different_readers_are_different_visitors(db_session, on_day):
    record_page_views(["/ledger"], READER, db_session)
    record_page_views(
        ["/ledger"], Client(ip="198.51.100.4", user_agent=READER.user_agent), db_session
    )
    assert len({e.visitor for e in db_session.query(AnalyticsEvent)}) == 2


def test_old_salts_and_events_age_out(db_session, on_day):
    record_page_views(["/ledger"], READER, db_session)
    on_day(DAY + EVENT_RETENTION_DAYS + 1)
    record_page_views(["/agora"], READER, db_session)

    assert [e.path for e in db_session.query(AnalyticsEvent)] == ["/agora"]
    assert [s.day for s in db_session.query(VisitorSalt)] == [DAY + EVENT_RETENTION_DAYS + 1]


@pytest.mark.parametrize(
    "agent", ["Googlebot/2.1", "curl/8.5.0", "python-httpx/0.28", "HeadlessChrome/140", ""]
)
def test_bots_and_scripts_are_not_counted(db_session, on_day, agent):
    assert record_page_views(["/ledger"], Client(ip="1.2.3.4", user_agent=agent), db_session) == 0
    assert db_session.query(AnalyticsEvent).count() == 0


def test_junk_paths_are_skipped_not_fatal(db_session, on_day):
    assert record_page_views(["/ledger", "https://x.example/", ""], READER, db_session) == 1


@pytest.mark.parametrize(
    ("metadata", "source"),
    [(None, "user"), ("{}", "user"), ('{"source": {"platform": "rss"}}', "scraped")],
)
def test_a_posts_content_source(create_user, create_post, metadata, source):
    post = create_post(create_user(username="author"))
    post.post_metadata = metadata
    assert content_source(post) == source
