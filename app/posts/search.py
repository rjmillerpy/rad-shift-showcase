"""Search + tag extraction. Public read-only."""

import json
from typing import Any

from sqlalchemy import ColumnElement, String, cast, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.auth.models import User

from .constants import MAX_TAG_RESULTS
from .models import PostModel
from .schema import PostResponse
from .serializer import (
    _exclude_drafts_query,
    _exclude_slopped_query,
    build_post_responses,
)


def search_posts_formatted(
    query: str,
    db: Session,
    current_user: User | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PostResponse], bool]:
    """Search posts by text content or tags in metadata."""
    pattern = f"%{query}%"
    base_query = (
        db.query(PostModel)
        .options(joinedload(PostModel.user), joinedload(PostModel.parent_post))
        .filter(PostModel.is_reply == False)  # noqa: E712
        .filter(
            or_(
                PostModel.text.ilike(pattern),
                cast(PostModel.post_metadata, String).ilike(pattern),
            )
        )
        .order_by(PostModel.unix_timestamp.desc())
    )
    filtered = _exclude_slopped_query(_exclude_drafts_query(base_query), current_user, db)
    all_posts = filtered.offset(offset).limit(limit + 1).all()
    has_more = len(all_posts) > limit
    return build_post_responses(all_posts[:limit], current_user, db), has_more


def search_users(
    query: str,
    db: Session,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list, bool]:
    """Search users by username."""
    pattern = f"%{query}%"
    users = (
        db.query(User)
        .filter(User.username.ilike(pattern))
        .order_by(User.username)
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    has_more = len(users) > limit
    results = [
        {
            "username": u.username,
            "bio": u.bio,
            "profile_picture_url": u.profile_picture_url,
        }
        for u in users[:limit]
    ]
    return results, has_more


def _tag_source_query(
    db: Session,
    feed: str,
    current_user: User | None,
) -> Query[Any]:
    """Return the SELECT of post_metadata rows for the given feed."""
    if feed == "algo":
        engagement: ColumnElement[Any] = (
            func.coalesce(PostModel.likes, 0)
            + func.coalesce(PostModel.reposts, 0)
            + func.coalesce(PostModel.shares, 0)
        )
        return (
            db.query(PostModel.post_metadata)
            .filter(
                PostModel.is_reply == False,  # noqa: E712
                PostModel.is_draft == False,  # noqa: E712
            )
            .order_by(engagement.desc())
            .limit(MAX_TAG_RESULTS)
        )
    if feed == "following" and current_user:
        followed_ids = [u.id for u in current_user.followed]
        return (
            db.query(PostModel.post_metadata)
            .filter(
                PostModel.user_id.in_(followed_ids),
                PostModel.is_reply == False,  # noqa: E712
                PostModel.is_draft == False,  # noqa: E712
            )
            .limit(MAX_TAG_RESULTS)
        )
    return (
        db.query(PostModel.post_metadata)
        .filter(
            PostModel.is_reply == False,  # noqa: E712
            PostModel.is_draft == False,  # noqa: E712
        )
        .order_by(PostModel.unix_timestamp.desc())
        .limit(MAX_TAG_RESULTS)
    )


def _extract_tags_from_meta(raw_meta: str | dict | None) -> list[str]:
    """Return a normalised list of tags for a single row of post_metadata."""
    if not raw_meta:
        return []
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except (json.JSONDecodeError, TypeError):
        return []
    tags = meta.get("tags")
    if isinstance(tags, str):
        return [t.strip() for t in tags.split("|") if t.strip()]
    if isinstance(tags, list):
        return [t.strip() for t in tags if isinstance(t, str) and t.strip()]
    return []


def get_feed_tags(
    db: Session,
    feed: str = "main",
    current_user: User | None = None,
    limit: int = 10,
) -> list[str]:
    """Extract unique tags from posts in a feed."""
    rows = _tag_source_query(db, feed, current_user).all()
    tag_set: set[str] = set()
    for (raw_meta,) in rows:
        tag_set.update(_extract_tags_from_meta(raw_meta))
    return sorted(tag_set)[:limit]


def get_full_metadata(post_metadata: str, db: Session) -> str | None:
    """Normalise a post's metadata JSON: split tags string; verify tagged users exist."""
    try:
        parsed = json.loads(post_metadata)
    except json.JSONDecodeError:
        return None
    if "tags" in parsed:
        raw_tags = parsed.get("tags", "")
        if isinstance(raw_tags, str):
            parsed["tags"] = raw_tags.split("|")
        elif isinstance(raw_tags, list):
            parsed["tags"] = raw_tags
        else:
            parsed["tags"] = []
    if "tagged_users" in parsed:
        tagged_usernames = parsed["tagged_users"]
        rows: list[Any] = db.query(User.username).filter(User.username.in_(tagged_usernames)).all()
        existing: set[str] = {row[0] for row in rows}
        parsed["tagged_users"] = [u for u in tagged_usernames if u in existing]
    return json.dumps(parsed)
