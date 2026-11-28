"""Tailored feeds: the reader's algo settings applied to ranking and filtering.

Boosts multiply a post's positive engagement (plus one, so a new post with no
reactions still moves), and the result is added to the feed's score:

    boost = (1 + PREFERRED_BOOST if it has a preferred topic)
          × (1 + FOLLOWED_BOOST if you follow its author)
          × (1 + INTEREST_BOOST × interest_adaptation × affinity)
          × (1 + RANDOM_SPREAD × randomness × jitter)
    score = feed score + (boost − 1) × (positive engagement + 1)

Affinity is how much of your recent reactions went to the post's best topic
(1 for your top topic). Jitter is a fixed number per post, reader and day,
so paging through a feed never repeats or skips a post.

Also here: blocked topics leave every feed's ranked results, reacted-to
posts can be hidden (nothing records which posts you only scrolled past),
and category diversity spreads a page's topics out.
"""

import time
import typing
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, Select, and_, case, cast, exists, func, literal, select, union_all
from sqlalchemy.orm import Query, Session

from app.auth.models import User, followers

from .models import PostLaugh, PostLike, PostModel, PostSave, PostShare, PostTopic, Repost
from .topics import normalize_topic

PREFERRED_BOOST = 1.0  # a preferred topic doubles what engagement earns
FOLLOWED_BOOST = 0.5
INTEREST_BOOST = 2.0  # at full adaptation, your top topic triples it
RANDOM_SPREAD = 1.0  # at full randomness, up to double
# Interests come from this many of your latest reactions of each kind.
INTEREST_REACTIONS = 200
INTEREST_TOPICS = 20
# At full diversity, a topic waits this many slots before it appears again.
MAX_DIVERSITY_GAP = 3
_JITTER_PRIME = 1_000_003
_JITTER_MULTIPLIER = 2_654_435_761  # Knuth's multiplicative hash
_DAY_SECONDS = 86_400


@dataclass(frozen=True)
class Tailoring:
    preferred: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    followed_boost: bool = True
    interest: float = 0.5
    randomness: float = 0.1
    diversity: float = 0.5
    hide_reacted: bool = False

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None) -> "Tailoring":
        s = settings or {}
        return cls(
            preferred=_topics(s.get("preferred_categories")),
            blocked=_topics(s.get("blocked_categories")),
            followed_boost=bool(s.get("show_followed_boost", cls.followed_boost)),
            interest=_unit(s.get("interest_adaptation", cls.interest)),
            randomness=_unit(s.get("randomness", cls.randomness)),
            diversity=_unit(s.get("category_diversity", cls.diversity)),
            # Stored as hide_seen_posts; see the module docstring.
            hide_reacted=bool(s.get("hide_seen_posts", cls.hide_reacted)),
        )


def reader_settings(viewer: User | None) -> dict[str, Any]:
    """The viewer's algo settings ({} when signed out or never saved)."""
    settings = typing.cast(dict[str, Any] | None, viewer.algo_settings) if viewer else None
    return settings or {}


def filter_posts(
    query: Query[PostModel], tailoring: Tailoring, viewer: User | None, db: Session
) -> Query[PostModel]:
    """Drop posts on blocked topics, and (if chosen) ones the viewer reacted to."""
    if tailoring.blocked:
        on_blocked = (
            select(PostTopic.post_id)
            .where(PostTopic.topic.in_(tailoring.blocked))
            .scalar_subquery()
        )
        query = query.filter(PostModel.id.not_in(on_blocked))
    if tailoring.hide_reacted and viewer is not None:
        query = query.filter(PostModel.id.not_in(_reacted_post_ids(viewer.id)))
    return query


def boost(tailoring: Tailoring, viewer: User | None, positive_engagement, db: Session):
    """What the reader's settings add to a post's score (an SQL expression).

    Nothing for signed-out readers: they have no settings, and a default
    shuffle would make the public feed's order change by the day.
    """
    if viewer is None:
        return literal(0.0)
    factor: Any = literal(1.0)
    if tailoring.preferred:
        factor = factor * case((_has_topic(tailoring.preferred), 1 + PREFERRED_BOOST), else_=1.0)
    if tailoring.followed_boost:
        follows = exists().where(
            and_(followers.c.follower_id == viewer.id, followers.c.followed_id == PostModel.user_id)
        )
        factor = factor * case((follows, 1 + FOLLOWED_BOOST), else_=1.0)
    interests = interests_of(viewer, db) if tailoring.interest else {}
    if interests:
        factor = factor * (1 + INTEREST_BOOST * tailoring.interest * _affinity(interests))
    if tailoring.randomness:
        viewer_id = typing.cast(int, viewer.id)
        seed = viewer_id * _DAY_SECONDS + int(time.time()) // _DAY_SECONDS
        factor = factor * (1 + RANDOM_SPREAD * tailoring.randomness * jitter(seed))
    return (factor - 1) * (positive_engagement + 1)


def jitter(seed: int):
    """A number in [0, 1) fixed per post and seed (an SQL expression, SQLite and Postgres).

    Integer arithmetic only, which both databases do the same. The squaring
    matters: a linear hash would only rotate one fixed order as the seed changed.
    """
    mixed = (PostModel.id * _JITTER_MULTIPLIER + seed % _JITTER_PRIME) % _JITTER_PRIME
    hashed = (mixed * mixed + PostModel.id) % _JITTER_PRIME
    return cast(hashed, Float) / _JITTER_PRIME


def interests_of(viewer: User, db: Session) -> dict[str, float]:
    """Topic → share of the viewer's recent reactions, scaled so the top topic is 1."""
    viewer_id = typing.cast(int, viewer.id)
    reacted = _recent_reacted_post_ids(viewer_id).subquery()
    count = func.count().label("count")
    counts: list[tuple[str, int]] = [
        (topic, n)
        for topic, n in db.query(PostTopic.topic, count)
        .join(reacted, reacted.c.post_id == PostTopic.post_id)
        .group_by(PostTopic.topic)
        .order_by(count.desc(), PostTopic.topic)
        .limit(INTEREST_TOPICS)
        .all()
    ]
    if not counts:
        return {}
    top = counts[0][1]
    return {topic: count / top for topic, count in counts}


def diversify(posts: list[PostModel], diversity: float, db: Session) -> list[PostModel]:
    """Reorder one page so a topic doesn't repeat within the last few slots."""
    gap = round(diversity * MAX_DIVERSITY_GAP)
    if gap == 0 or len(posts) < 2:
        return posts
    ids = [typing.cast(int, post.id) for post in posts]
    topics: dict[int, set[str]] = {post_id: set() for post_id in ids}
    rows = db.query(PostTopic.post_id, PostTopic.topic).filter(PostTopic.post_id.in_(ids))
    for post_id, topic in rows:
        topics[post_id].add(topic)
    by_post = dict(zip(ids, posts, strict=True))
    remaining: list[int] = list(ids)
    ordered: list[int] = []
    while remaining:
        recent: set[str] = set().union(*(topics[post_id] for post_id in ordered[-gap:]))
        pick = next((i for i in remaining if not topics[i] & recent), remaining[0])
        remaining.remove(pick)
        ordered.append(pick)
    return [by_post[post_id] for post_id in ordered]


def _has_topic(topics: tuple[str, ...]):
    return exists().where(and_(PostTopic.post_id == PostModel.id, PostTopic.topic.in_(topics)))


def _affinity(interests: dict[str, float]):
    weight = case(
        *((PostTopic.topic == topic, share) for topic, share in interests.items()), else_=0.0
    )
    best = (
        select(func.max(weight))
        .where(PostTopic.post_id == PostModel.id)
        .correlate(PostModel)
        .scalar_subquery()
    )
    return func.coalesce(best, 0.0)


def _reacted_post_ids(user_id: int):
    return union_all(*_reaction_selects(user_id, limit=None)).scalar_subquery()


def _recent_reacted_post_ids(user_id: int):
    return union_all(*_reaction_selects(user_id, limit=INTEREST_REACTIONS))


def _reaction_selects(user_id: int, limit: int | None):
    tables = (
        (PostLike, PostLike.post_id, PostLike.id),
        (PostLaugh, PostLaugh.post_id, PostLaugh.id),
        (PostSave, PostSave.post_id, PostSave.id),
        (PostShare, PostShare.post_id, PostShare.id),
        (Repost, Repost.original_post_id, Repost.id),
    )
    selects: list[Select[tuple[int]]] = []
    for model, post_id, row_id in tables:
        query: Select[tuple[int]] = select(post_id.label("post_id")).where(model.user_id == user_id)
        if limit is not None:
            # A subquery each, so the limit applies per kind (SQLite needs it wrapped).
            query = select(query.order_by(row_id.desc()).limit(limit).subquery().c.post_id)
        selects.append(query)
    return selects


def _topics(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    topics = (normalize_topic(item) for item in raw if isinstance(item, str))
    return tuple(dict.fromkeys(topic for topic in topics if topic))


def _unit(raw: Any) -> float:
    try:
        return min(1.0, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0
