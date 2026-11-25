"""app/ratelimit/service.py: the fixed-window counter."""

from app.ratelimit.constants import STALE_WINDOW_SECONDS, Policy
from app.ratelimit.models import RateLimitWindow
from app.ratelimit.service import hit

POLICY = Policy("test", limit=3, window_seconds=60, per_user=False)
T0 = 1_800_000_000  # a window boundary (divisible by 60)


def test_allows_up_to_the_limit_then_refuses(db_session):
    decisions = [hit(db_session, POLICY, "ip:1.2.3.4", T0 + i) for i in range(4)]
    assert [d.allowed for d in decisions] == [True, True, True, False]


def test_retry_after_is_the_time_left_in_the_window(db_session):
    for _ in range(3):
        hit(db_session, POLICY, "ip:1.2.3.4", T0)
    assert hit(db_session, POLICY, "ip:1.2.3.4", T0 + 45).retry_after == 15


def test_each_identity_has_its_own_count(db_session):
    for _ in range(3):
        hit(db_session, POLICY, "ip:1.2.3.4", T0)
    assert hit(db_session, POLICY, "ip:5.6.7.8", T0).allowed


def test_a_new_window_starts_from_zero_and_drops_the_old_row(db_session):
    for _ in range(4):
        hit(db_session, POLICY, "ip:1.2.3.4", T0)
    assert hit(db_session, POLICY, "ip:1.2.3.4", T0 + 60).allowed
    assert [r.window_start for r in db_session.query(RateLimitWindow).all()] == [T0 + 60]


def test_rows_older_than_a_day_are_cleaned_up_by_anyone(db_session):
    hit(db_session, POLICY, "ip:old", T0)
    later = T0 + STALE_WINDOW_SECONDS + 60
    hit(db_session, POLICY, "ip:new", later)
    assert [r.key for r in db_session.query(RateLimitWindow).all()] == ["test:ip:new"]
