"""Tests for app/engagement/trending.py: decaying scores, idempotent folding, ranking."""

import pytest

from app.engagement.constants import (
    HALF_LIFE_SECONDS,
    TRENDING_CANDIDATES,
    TRENDING_MIN_SCORE,
    TRENDING_WINDOW_SECONDS,
)
from app.engagement.models import PostTrending, ProcessedPostEvent
from app.engagement.schema import EVENT_WEIGHTS, PostEventType
from app.engagement.trending import apply_event, decayed, prune_processed, ranked_post_ids

from .conftest import event

T0 = 1_000_000.0


class TestDecayed:
    def test_halves_every_half_life(self):
        assert decayed(8.0, T0, T0 + 2 * HALF_LIFE_SECONDS) == pytest.approx(2.0)

    def test_no_time_no_change(self):
        assert decayed(5.0, T0, T0) == 5.0

    def test_never_grows_backwards_in_time(self):
        assert decayed(5.0, T0, T0 - HALF_LIFE_SECONDS) == 5.0


@pytest.fixture()
def post(create_user, create_post):
    return create_post(user=create_user(username="author"))


def score(db, post_id):
    row = db.get(PostTrending, post_id)
    return None if row is None else (row.score, row.updated_at)


class TestApplyEvent:
    def test_the_first_event_starts_the_score(self, db_session, post):
        assert apply_event(db_session, event(PostEventType.SAVED, post.id, T0)) is True

        assert score(db_session, post.id) == (EVENT_WEIGHTS[PostEventType.SAVED], T0)

    def test_a_later_event_adds_to_the_decayed_score(self, db_session, post):
        apply_event(db_session, event(PostEventType.REPOSTED, post.id, T0))
        apply_event(db_session, event(PostEventType.LIKED, post.id, T0 + HALF_LIFE_SECONDS))

        value, updated_at = score(db_session, post.id)
        assert value == pytest.approx(3.0 / 2 + 1.0)
        assert updated_at == T0 + HALF_LIFE_SECONDS

    def test_a_late_event_counts_as_of_its_own_time(self, db_session, post):
        apply_event(db_session, event(PostEventType.LIKED, post.id, T0 + HALF_LIFE_SECONDS))
        apply_event(db_session, event(PostEventType.REPOSTED, post.id, T0))

        value, updated_at = score(db_session, post.id)
        assert value == pytest.approx(1.0 + 3.0 / 2)
        assert updated_at == T0 + HALF_LIFE_SECONDS

    def test_an_undo_cancels_its_action(self, db_session, post):
        apply_event(db_session, event(PostEventType.LIKED, post.id, T0))
        apply_event(db_session, event(PostEventType.UNLIKED, post.id, T0))

        assert score(db_session, post.id)[0] == pytest.approx(0.0)

    def test_a_redelivered_event_changes_nothing(self, db_session, post):
        liked = event(PostEventType.LIKED, post.id, T0)
        apply_event(db_session, liked)

        assert apply_event(db_session, liked) is False
        assert score(db_session, post.id)[0] == 1.0

    def test_an_event_for_a_deleted_post_is_remembered_and_skipped(self, db_session):
        gone = event(PostEventType.LIKED, post_id=999, occurred_at=T0)

        assert apply_event(db_session, gone) is True
        assert db_session.get(PostTrending, 999) is None
        assert apply_event(db_session, gone) is False


class TestRankedPostIds:
    def make_posts(self, create_user, create_post, count):
        user = create_user(username="ranker")
        return [create_post(user=user, text=f"p{i}").id for i in range(count)]

    def test_ranks_by_score_as_of_now(self, db_session, create_user, create_post):
        old_hit, fresh, older = self.make_posts(create_user, create_post, 3)
        # Six shares a day ago (6 * 3 / 16 = 1.125 now) vs two likes just now.
        for i in range(6):
            apply_event(db_session, event(PostEventType.SHARED, old_hit, T0, event_id=f"s{i}"))
        for i in range(2):
            apply_event(
                db_session,
                event(PostEventType.LIKED, fresh, T0 + 4 * HALF_LIFE_SECONDS, event_id=f"l{i}"),
            )
        apply_event(db_session, event(PostEventType.LIKED, older, T0 + 3 * HALF_LIFE_SECONDS))

        assert ranked_post_ids(db_session, now=T0 + 4 * HALF_LIFE_SECONDS) == [
            fresh,
            old_hit,
            older,
        ]

    def test_posts_decayed_below_the_floor_drop_out(self, db_session, create_user, create_post):
        (post_id,) = self.make_posts(create_user, create_post, 1)
        apply_event(db_session, event(PostEventType.LIKED, post_id, T0))
        # Just above and just below TRENDING_MIN_SCORE.
        halvings_to_floor = 0
        while 2**-halvings_to_floor >= TRENDING_MIN_SCORE:
            halvings_to_floor += 1

        assert ranked_post_ids(db_session, T0 + (halvings_to_floor - 1) * HALF_LIFE_SECONDS) == [
            post_id
        ]
        assert ranked_post_ids(db_session, T0 + halvings_to_floor * HALF_LIFE_SECONDS) == []

    def test_a_cancelled_post_does_not_trend(self, db_session, create_user, create_post):
        (post_id,) = self.make_posts(create_user, create_post, 1)
        apply_event(db_session, event(PostEventType.SAVED, post_id, T0))
        apply_event(db_session, event(PostEventType.UNSAVED, post_id, T0))

        assert ranked_post_ids(db_session, T0) == []

    def test_only_recent_activity_is_considered(self, db_session, create_user, create_post):
        (post_id,) = self.make_posts(create_user, create_post, 1)
        db_session.add(PostTrending(post_id=post_id, score=1e9, updated_at=T0))
        db_session.commit()

        assert ranked_post_ids(db_session, T0 + TRENDING_WINDOW_SECONDS + 1) == []

    def test_candidates_are_capped(self, db_session, create_user, create_post):
        user = create_user(username="many")
        for i in range(TRENDING_CANDIDATES + 5):
            post = create_post(user=user, text=f"m{i}")
            db_session.add(PostTrending(post_id=post.id, score=1.0, updated_at=T0 + i))
        db_session.commit()

        assert len(ranked_post_ids(db_session, T0 + TRENDING_CANDIDATES + 5)) == TRENDING_CANDIDATES


def test_prune_forgets_only_old_event_ids(db_session):
    db_session.add_all(
        [
            ProcessedPostEvent(event_id="old", processed_at=T0),
            ProcessedPostEvent(event_id="new", processed_at=T0 + 10),
        ]
    )
    db_session.commit()

    assert prune_processed(db_session, older_than=T0 + 5) == 1
    assert [e.event_id for e in db_session.query(ProcessedPostEvent)] == ["new"]
