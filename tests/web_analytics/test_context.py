"""Tests for app/web_analytics/context.py outside a request (inside one: test_views.py)."""

from app.web_analytics.context import current, record_engagement_here
from app.web_analytics.models import AnalyticsEvent


def test_outside_a_request_there_is_no_context_and_nothing_is_recorded(
    db_session, create_user, create_post
):
    post = create_post(create_user(username="author"))
    assert current() is None
    record_engagement_here("like", post, db_session)
    assert db_session.query(AnalyticsEvent).count() == 0
