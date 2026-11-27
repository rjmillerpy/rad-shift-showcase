"""Recording page views and engagements, and reporting on them.

Recording never fails the request it rides on: analytics is best-effort, so a
problem here is logged and dropped, never shown to a reader.
"""

import hashlib
import logging
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.posts.models import PostModel
from app.posts.serializer import get_metadata

from .constants import (
    BOT_USER_AGENT,
    DAY_SECONDS,
    EVENT_RETENTION_DAYS,
    FEED_MODES,
    ID_SEGMENTS,
    MAX_PATH_LENGTH,
    SALT_BYTES,
    SALT_KEEP_DAYS,
    VISITOR_HASH_LENGTH,
    ContentSource,
    EventType,
)
from .models import AnalyticsEvent, VisitorSalt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Client:
    """Who sent the request, as far as analytics may know: never stored as is."""

    ip: str
    user_agent: str

    @property
    def is_bot(self) -> bool:
        return not self.user_agent or bool(BOT_USER_AGENT.search(self.user_agent))


def record_page_views(paths: Iterable[str], client: Client, db: Session) -> int:
    """Store page views; returns how many were kept (bots and junk paths aren't)."""
    if client.is_bot:
        return 0
    now = int(time.time())
    visitor = _visitor(client, now, db)
    events = [
        AnalyticsEvent(
            occurred_at=now,
            day=now // DAY_SECONDS,
            visitor=visitor,
            event_type=EventType.PAGE_VIEW.value,
            path=path,
            mode=mode_of(path),
        )
        for path in filter(None, map(clean_path, paths))
    ]
    db.add_all(events)
    db.commit()
    return len(events)


def record_engagement(
    action: str, post: PostModel, mode: str | None, client: Client, db: Session
) -> None:
    """One engagement (like, repost...) on a post, from the reader's feed mode."""
    if client.is_bot:
        return
    try:
        now = int(time.time())
        db.add(
            AnalyticsEvent(
                occurred_at=now,
                day=now // DAY_SECONDS,
                visitor=_visitor(client, now, db),
                event_type=EventType.ENGAGEMENT.value,
                mode=mode if mode in FEED_MODES else None,
                action=action,
                post_id=post.id,
                source=content_source(post),
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("analytics.engagement.dropped")


def clean_path(raw: str) -> str | None:
    """A page's path without query, fragment, ids or names; None if it isn't one."""
    path = raw.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/") or path.startswith("//"):
        return None
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) >= 2 and segments[0] in ID_SEGMENTS:
        segments[1] = ID_SEGMENTS[segments[0]]
    return ("/" + "/".join(segments))[:MAX_PATH_LENGTH]


def mode_of(path: str) -> str | None:
    first = path.strip("/").split("/", 1)[0]
    return first if first in FEED_MODES else None


def content_source(post: PostModel) -> str:
    scraped = "source" in get_metadata(post)
    return ContentSource.SCRAPED.value if scraped else ContentSource.USER.value


def _visitor(client: Client, now: int, db: Session) -> str:
    material = f"{_salt(now // DAY_SECONDS, db)}|{client.ip}|{client.user_agent}"
    return hashlib.sha256(material.encode()).hexdigest()[:VISITOR_HASH_LENGTH]


def _salt(day: int, db: Session) -> str:
    row = db.get(VisitorSalt, day)
    if row is not None:
        return row.salt
    # The day's first event: make its salt, and clear out what has aged out.
    db.add(VisitorSalt(day=day, salt=secrets.token_hex(SALT_BYTES)))
    try:
        db.flush()
    except IntegrityError:
        # Another request made today's salt first; use theirs.
        db.rollback()
        return db.get(VisitorSalt, day).salt  # type: ignore[union-attr]
    db.query(VisitorSalt).filter(VisitorSalt.day < day - SALT_KEEP_DAYS + 1).delete()
    db.query(AnalyticsEvent).filter(AnalyticsEvent.day < day - EVENT_RETENTION_DAYS).delete()
    return db.get(VisitorSalt, day).salt  # type: ignore[union-attr]
