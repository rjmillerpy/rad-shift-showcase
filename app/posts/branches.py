"""Content branches: topics next to the ones you follow, and the posts on them.

Your roots are the topics you follow (Bubbles topics, preferred topics) and
the ones you react to most (app/posts/tailoring.interests_of). A branch is a
topic that shares posts with a root but isn't one yet:

    score = shared posts / √(posts on the branch) × the root's weight

so a topic that only turns up next to yours beats one that is everywhere.
Following a branch makes it a root, and the tree grows from there.

This picks from what's already posted (people's and scraped). Writing new
posts for a thin branch with a model is the paid version, left until
go-live (product roadmap, Phase 3).
"""

import math
import typing
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.auth.models import User
from app.common.utils import paginate
from app.profile.constants import DEFAULT_BUBBLE_SETTINGS

from .feeds import algo_ranked_query, visible_to
from .models import PostModel, PostTopic
from .schema import PostResponse
from .serializer import build_post_responses
from .tailoring import Tailoring, interests_of, reader_settings
from .topics import normalize_topic

MAX_BRANCHES = 8
# Topics shared by fewer posts than this are coincidence, not a branch.
MIN_SHARED_POSTS = 2
# Branches come from this many of the newest posts.
RECENT_POSTS = 5000
FOLLOWED_WEIGHT = 1.0  # an interest weighs its share of your reactions (top = 1)
MAX_FOLLOWED_TOPICS = 50


@dataclass(frozen=True)
class Branch:
    topic: str
    via: str  # the root it grew from
    posts: int  # posts on it, among the recent ones
    score: float


def roots_of(viewer: User, db: Session) -> dict[str, float]:
    """Topic → weight: followed topics at FOLLOWED_WEIGHT, interests at their share."""
    roots = dict(interests_of(viewer, db))
    for topic in followed_topics(viewer) + list(
        Tailoring.from_settings(reader_settings(viewer)).preferred
    ):
        roots[topic] = FOLLOWED_WEIGHT
    return roots


def branches_for(viewer: User, db: Session) -> list[Branch]:
    roots = roots_of(viewer, db)
    if not roots:
        return []
    excluded = set(roots) | _unwanted(viewer)
    shared = _shared_posts(list(roots), db)
    popularity = _post_counts({topic for topic, _root, _n in shared}, db)
    best: dict[str, Branch] = {}
    for topic, root, count in shared:
        if topic in excluded or count < MIN_SHARED_POSTS:
            continue
        score = count / math.sqrt(popularity[topic]) * roots[root]
        if topic not in best or score > best[topic].score:
            best[topic] = Branch(topic, root, popularity[topic], score)
    ranked = sorted(best.values(), key=lambda b: (-b.score, b.topic))
    return ranked[:MAX_BRANCHES]


def branch_post_ids(branches: list[Branch]):
    """Posts on any of these branches (an SQL subquery)."""
    return (
        select(PostTopic.post_id)
        .where(PostTopic.topic.in_([b.topic for b in branches]))
        .scalar_subquery()
    )


def get_branch_posts_formatted(
    db: Session, viewer: User, offset: int = 0, limit: int = 20
) -> tuple[list[Branch], list[PostResponse], bool]:
    """The viewer's branches, and the posts on them in the viewer's algo order."""
    branches = branches_for(viewer, db)
    if not branches:
        return [], [], False
    on_branches = algo_ranked_query(db, viewer).filter(PostModel.id.in_(branch_post_ids(branches)))
    posts, has_more = paginate(visible_to(on_branches, viewer, db), offset, limit)
    return branches, build_post_responses(posts, viewer, db), has_more


def followed_topics(viewer: User) -> list[str]:
    raw = _bubble_settings(viewer).get("custom_topics") or []
    topics = (normalize_topic(t) for t in raw if isinstance(t, str))
    return list(dict.fromkeys(t for t in topics if t))


def follow(viewer: User, raw_topic: str, db: Session) -> list[str]:
    """Add a topic to the viewer's Bubbles topics, which roots branches. Returns them."""
    topic = normalize_topic(raw_topic)
    if topic is None:
        raise HTTPException(status_code=422, detail="Topic is empty")
    current = followed_topics(viewer)
    if topic not in current:
        if len(current) >= MAX_FOLLOWED_TOPICS:
            raise HTTPException(status_code=400, detail="You follow too many topics already")
        current.append(topic)
    return _save_followed(viewer, current, db)


def unfollow(viewer: User, raw_topic: str, db: Session) -> list[str]:
    topic = normalize_topic(raw_topic)
    return _save_followed(viewer, [t for t in followed_topics(viewer) if t != topic], db)


def _save_followed(viewer: User, topics: list[str], db: Session) -> list[str]:
    # A new dict, so SQLAlchemy sees the JSON column change.
    viewer.bubble_settings = {**_bubble_settings(viewer), "custom_topics": topics}  # type: ignore[assignment]
    db.commit()
    return topics


def _bubble_settings(viewer: User) -> dict[str, Any]:
    saved = typing.cast(dict[str, Any] | None, viewer.bubble_settings) or {}
    return {**DEFAULT_BUBBLE_SETTINGS, **saved}


def _unwanted(viewer: User) -> set[str]:
    blocked = Tailoring.from_settings(reader_settings(viewer)).blocked
    hidden = _bubble_settings(viewer).get("hidden_topics") or []
    topics = (normalize_topic(raw) for raw in hidden if isinstance(raw, str))
    return set(blocked) | {topic for topic in topics if topic}


def _recent_post_ids():
    newest = select(PostModel.id).order_by(PostModel.id.desc()).limit(RECENT_POSTS).subquery()
    return select(newest.c.id)


def _shared_posts(roots: list[str], db: Session) -> list[tuple[str, str, int]]:
    """(topic, root, posts with both) for every topic sharing a recent post with a root."""
    root, other = aliased(PostTopic), aliased(PostTopic)
    rows = (
        db.query(other.topic, root.topic, func.count(func.distinct(root.post_id)))
        .join(other, (other.post_id == root.post_id) & (other.topic != root.topic))
        .filter(root.topic.in_(roots), root.post_id.in_(_recent_post_ids()))
        .group_by(other.topic, root.topic)
    )
    return [(topic, via, int(count)) for topic, via, count in rows]


def _post_counts(topics: set[str], db: Session) -> dict[str, int]:
    if not topics:
        return {}
    rows = (
        db.query(PostTopic.topic, func.count())
        .filter(PostTopic.topic.in_(topics), PostTopic.post_id.in_(_recent_post_ids()))
        .group_by(PostTopic.topic)
    )
    return {topic: int(count) for topic, count in rows}
