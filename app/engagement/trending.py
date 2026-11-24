"""Trending scores: folding events in (the aggregator) and ranking (GET /posts/trending).

A score halves every HALF_LIFE_SECONDS. Storing (score, updated_at) is
enough to know it at any later time, so nothing has to rewrite every row
as time passes: decay is applied when an event arrives and when ranking.
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.posts.models import PostModel

from .constants import (
    HALF_LIFE_SECONDS,
    LOG_EVENT_NO_POST,
    TRENDING_CANDIDATES,
    TRENDING_MIN_SCORE,
    TRENDING_WINDOW_SECONDS,
)
from .models import PostTrending, ProcessedPostEvent
from .schema import EVENT_WEIGHTS, PostEvent

logger = logging.getLogger(__name__)


def decayed(score: float, since: float, now: float) -> float:
    """`score` as of `since`, decayed to `now` (never grows: no negative ages)."""
    return float(score * 2 ** (-max(now - since, 0.0) / HALF_LIFE_SECONDS))


def apply_event(db: Session, event: PostEvent) -> bool:
    """Fold one event into its post's score and commit; False if it was already applied.

    The event id is stored in the same transaction as the score, so a
    redelivery after a crash (Kafka delivers at least once) finds it and
    changes nothing. Events for one post arrive in order (they share a
    partition), but the score is right even if one is late: each side is
    decayed to the newer of the two times.
    """
    if db.get(ProcessedPostEvent, event.event_id) is not None:
        return False
    db.add(ProcessedPostEvent(event_id=event.event_id, processed_at=time.time()))
    post_exists = db.execute(
        select(PostModel.__table__.c.id).where(PostModel.__table__.c.id == event.post_id)
    ).first()
    if post_exists is None:
        # Deleted since; remembered as processed so a replay skips it too.
        logger.info(LOG_EVENT_NO_POST, extra={"post_id": event.post_id})
        db.commit()
        return True
    weight = EVENT_WEIGHTS[event.type]
    row = db.get(PostTrending, event.post_id)
    if row is None:
        db.add(PostTrending(post_id=event.post_id, score=weight, updated_at=event.occurred_at))
    else:
        newest = max(row.updated_at, event.occurred_at)
        row.score = decayed(row.score, row.updated_at, newest) + decayed(
            weight, event.occurred_at, newest
        )
        row.updated_at = newest
    db.commit()
    return True


def ranked_post_ids(db: Session, now: float) -> list[int]:
    """Post ids by current score, highest first; only posts still trending."""
    rows = (
        db.query(PostTrending)
        .filter(PostTrending.updated_at >= now - TRENDING_WINDOW_SECONDS)
        .order_by(PostTrending.updated_at.desc())
        .limit(TRENDING_CANDIDATES)
        .all()
    )
    scored = [(decayed(row.score, row.updated_at, now), row.post_id) for row in rows]
    return [
        post_id for score, post_id in sorted(scored, reverse=True) if score >= TRENDING_MIN_SCORE
    ]


def prune_processed(db: Session, older_than: float) -> int:
    """Forget event ids processed before `older_than`; returns how many."""
    deleted = (
        db.query(ProcessedPostEvent)
        .filter(ProcessedPostEvent.processed_at < older_than)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
