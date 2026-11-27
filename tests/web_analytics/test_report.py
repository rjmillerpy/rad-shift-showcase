"""Tests for app/web_analytics/report.py: the numbers the admin dashboard shows."""

from app.web_analytics.constants import DAY_SECONDS
from app.web_analytics.models import AnalyticsEvent
from app.web_analytics.report import traffic_since

DAY = 20_000


def _event(
    db,
    day,
    visitor,
    kind="page_view",
    path="/ledger",
    mode="ledger",
    action=None,
    post_id=None,
    source=None,
):
    db.add(AnalyticsEvent(occurred_at=day * DAY_SECONDS, day=day, visitor=visitor, event_type=kind, path=path,
                          mode=mode, action=action, post_id=post_id, source=source))  # fmt: skip


def test_traffic_per_day_counts_views_and_distinct_visitors(db_session):
    for visitor in ("a", "a", "b"):
        _event(db_session, DAY, visitor)
    _event(db_session, DAY + 1, "c")
    db_session.commit()

    traffic = traffic_since(DAY * DAY_SECONDS, db_session)

    assert traffic.days == [
        {"day": DAY * DAY_SECONDS, "views": 3, "visitors": 2},
        {"day": (DAY + 1) * DAY_SECONDS, "views": 1, "visitors": 1},
    ]


def test_engagement_rate_per_mode_and_engagement_per_source(db_session):
    for visitor in "abcd":
        _event(db_session, DAY, visitor, path="/ledger", mode="ledger")
    _event(db_session, DAY, "e", path="/agora", mode="agora")
    _event(
        db_session,
        DAY,
        "a",
        "engagement",
        path=None,
        mode="ledger",
        action="like",
        post_id=1,
        source="user",
    )
    _event(
        db_session,
        DAY,
        "e",
        "engagement",
        path=None,
        mode="agora",
        action="like",
        post_id=2,
        source="scraped",
    )
    _event(
        db_session,
        DAY,
        "e",
        "engagement",
        path=None,
        mode="agora",
        action="save",
        post_id=2,
        source="scraped",
    )
    db_session.commit()

    traffic = traffic_since(DAY * DAY_SECONDS, db_session)

    assert traffic.by_mode == [
        {"mode": "ledger", "views": 4, "visitors": 4, "engagements": 1, "engagement_rate": 0.25},
        {"mode": "agora", "views": 1, "visitors": 1, "engagements": 2, "engagement_rate": 2.0},
    ]
    assert traffic.by_source == [
        {"source": "scraped", "engagements": 2, "posts": 1},
        {"source": "user", "engagements": 1, "posts": 1},
    ]
    assert traffic.top_pages == [{"path": "/ledger", "views": 4}, {"path": "/agora", "views": 1}]


def test_engagement_with_no_views_has_no_rate(db_session):
    _event(
        db_session,
        DAY,
        "a",
        "engagement",
        path=None,
        mode="amble",
        action="like",
        post_id=1,
        source="user",
    )
    db_session.commit()
    (row,) = traffic_since(DAY * DAY_SECONDS, db_session).by_mode
    assert row["engagement_rate"] is None


def test_older_events_are_outside_the_range(db_session):
    _event(db_session, DAY - 1, "old")
    db_session.commit()
    assert traffic_since(DAY * DAY_SECONDS, db_session).days == []
