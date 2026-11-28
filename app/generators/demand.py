"""Topics readers want: what people follow, and how much there is to read on it.

A topic is followed when it's in someone's Bubbles topics or preferred
topics (the roots of app/posts/branches.py). One with few recent posts is
thin, and a source made from a template that takes a topic
(app/generators/templates.py) is the free way to fill it.
"""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.models import User
from app.posts.branches import RECENT_POSTS, followed_topics
from app.posts.models import PostModel, PostTopic
from app.posts.tailoring import Tailoring, reader_settings

MAX_WANTED_TOPICS = 20
# Fewer recent posts than this and a followed topic is thin.
THIN_BELOW = 10
# Readers scanned per request, so the admin page stays fast as the site grows.
MAX_READERS_SCANNED = 20_000
_TIE_MARGIN = 10


@dataclass(frozen=True)
class WantedTopic:
    topic: str
    readers: int
    posts: int  # among the newest RECENT_POSTS

    @property
    def thin(self) -> bool:
        return self.posts < THIN_BELOW


def wanted_topics(db: Session) -> list[WantedTopic]:
    """The most-followed topics: most readers first, then the thinnest (it needs a source most)."""
    readers: Counter[str] = Counter()
    with_settings = (
        db.query(User)
        .filter(or_(User.bubble_settings.is_not(None), User.algo_settings.is_not(None)))
        .filter(User.is_banned.is_(False))
        .order_by(User.id.desc())
        .limit(MAX_READERS_SCANNED)
    )
    for user in with_settings:
        follows = set(followed_topics(user)) | set(
            Tailoring.from_settings(reader_settings(user)).preferred
        )
        readers.update(follows)
    # Ties are broken by post counts, so count a margin past the cut, not every topic.
    candidates = readers.most_common(MAX_WANTED_TOPICS * _TIE_MARGIN)
    counts = _recent_post_counts([topic for topic, _ in candidates], db)
    wanted = [WantedTopic(topic, n, counts.get(topic, 0)) for topic, n in candidates]
    wanted.sort(key=lambda w: (-w.readers, w.posts, w.topic))
    return wanted[:MAX_WANTED_TOPICS]


def _recent_post_counts(topics: list[str], db: Session) -> dict[str, int]:
    if not topics:
        return {}
    newest = db.query(PostModel.id).order_by(PostModel.id.desc()).limit(RECENT_POSTS).subquery()
    rows = (
        db.query(PostTopic.topic, func.count())
        .filter(PostTopic.topic.in_(topics), PostTopic.post_id.in_(db.query(newest.c.id)))
        .group_by(PostTopic.topic)
    )
    return {topic: int(n) for topic, n in rows}
