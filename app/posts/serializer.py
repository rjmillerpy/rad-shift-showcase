"""Batch-serialise `PostModel` rows into `PostResponse` value objects.

Splitting this out of ``service.py`` keeps the CRUD file small and gives feeds
+ single-post fetch a single shared code path (avoids the N+1 patterns rule 21
warns against).
"""

import json
from typing import Any

from sqlalchemy import UnaryExpression, func
from sqlalchemy.orm import Query, Session

from app.auth.models import User

from .models import PostLaugh, PostLike, PostModel, PostSave, Repost, Slop
from .schema import PostResponse


def get_ordered_model(desc: bool) -> UnaryExpression:
    """Return the timestamp ordering clause for a post query."""
    return PostModel.unix_timestamp.desc() if desc else PostModel.unix_timestamp.asc()


def get_metadata(post: PostModel) -> dict:
    """Parse the JSON post_metadata column; empty dict on any failure."""
    try:
        return json.loads(post.post_metadata) if post.post_metadata else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _exclude_drafts_query(base_query: Query[PostModel]) -> Query[PostModel]:
    return base_query.filter(PostModel.is_draft == False)  # noqa: E712


def _exclude_slopped_query(
    base_query: Query[PostModel], current_user: User | None, db: Session
) -> Query[PostModel]:
    """Apply the user's slop_filter setting to `base_query`.

    Modes:
      - "show": no filter, everything visible.
      - "hide" / "dim" (default): exclude posts this user has slopped/reported.
        "dim" is a frontend-only visual mode — the backend treats it as "hide".
      - "only": inverse mode — include ONLY posts whose community slop count
        is >= slop_threshold (min 1). Lets a user opt into a heavy-slop feed.
    """
    if not current_user:
        return base_query
    algo_settings: dict[str, Any] = current_user.algo_settings or {}
    slop_filter = algo_settings.get("slop_filter", "hide")

    if slop_filter == "show":
        return base_query

    if slop_filter == "only":
        # Coerce threshold to >=1: a threshold of 0 would let posts with no
        # slop marks through, which contradicts what "only heavily-slopped" means.
        threshold = max(1, int(algo_settings.get("slop_threshold", 0) or 0))
        slop_count_sq = (
            db.query(Slop.post_id, func.count(Slop.id).label("cnt"))
            .group_by(Slop.post_id)
            .subquery()
        )
        return base_query.outerjoin(slop_count_sq, PostModel.id == slop_count_sq.c.post_id).filter(
            func.coalesce(slop_count_sq.c.cnt, 0) >= threshold
        )

    # Default: hide posts the current user has personally slopped.
    slopped_ids = db.query(Slop.post_id).filter(Slop.user_id == current_user.id).scalar_subquery()
    return base_query.filter(~PostModel.id.in_(slopped_ids))


def build_quoted_post(post: PostModel) -> dict | None:
    """Return a small dict describing the parent post being quoted, or None."""
    if not post.parent_post_id or not post.parent_post:
        return None
    parent = post.parent_post
    return {
        "id": parent.id,
        "username": parent.user.username if parent.user else None,
        "text": parent.text,
    }


def _batch_replies_and_quotes(
    post_ids: list[int],
    db: Session,
) -> tuple[dict[int, int], dict[int, int]]:
    replies_counts: dict[int, int] = dict(
        db.query(PostModel.parent_post_id, func.count(PostModel.id))
        .filter(
            PostModel.parent_post_id.in_(post_ids),
            PostModel.is_reply == True,  # noqa: E712
            PostModel.is_draft == False,  # noqa: E712
        )
        .group_by(PostModel.parent_post_id)
        .all()
    )
    quotes_counts: dict[int, int] = dict(
        db.query(PostModel.parent_post_id, func.count(PostModel.id))
        .filter(
            PostModel.parent_post_id.in_(post_ids),
            PostModel.is_reply == False,  # noqa: E712
            PostModel.is_draft == False,  # noqa: E712
        )
        .group_by(PostModel.parent_post_id)
        .all()
    )
    return replies_counts, quotes_counts


def _batch_slop_counts(post_ids: list[int], db: Session) -> dict[int, int]:
    return dict(
        db.query(Slop.post_id, func.count(Slop.id))
        .filter(Slop.post_id.in_(post_ids))
        .group_by(Slop.post_id)
        .all()
    )


# Interaction name -> (column holding the post id, column holding the user id).
_INTERACTION_COLUMNS = {
    "liked": (PostLike.post_id, PostLike.user_id),
    "reposted": (Repost.original_post_id, Repost.user_id),
    "saved": (PostSave.post_id, PostSave.user_id),
    "laughed": (PostLaugh.post_id, PostLaugh.user_id),
}


def _batch_interaction_ids(
    post_ids: list[int],
    current_user: User | None,
    db: Session,
) -> dict[str, set]:
    """Return sets of {liked, reposted, saved, laughed} post ids for `current_user`.

    One query per interaction type for the whole page of posts (rule 21),
    never one per post.
    """
    if current_user is None:
        return {name: set() for name in _INTERACTION_COLUMNS}
    return {
        name: {
            row[0]
            for row in db.query(post_column)
            .filter(user_column == current_user.id, post_column.in_(post_ids))
            .all()
        }
        for name, (post_column, user_column) in _INTERACTION_COLUMNS.items()
    }


def _build_single_response(
    post: PostModel,
    *,
    current_user: User | None,
    replies_counts: dict[int, int],
    quotes_counts: dict[int, int],
    slop_counts: dict[int, int],
    interactions: dict[str, set],
    followed_ids: set[int],
    repost_map: dict | None,
    saved_override: bool | None,
) -> PostResponse:
    is_me = bool(current_user and post.user.id == current_user.id)
    is_saved = saved_override if saved_override is not None else post.id in interactions["saved"]
    return PostResponse(
        id=post.id,
        text=post.text,
        unix_timestamp=post.unix_timestamp,
        post_metadata=get_metadata(post),
        username=post.user.username,
        profile_picture_url=post.user.profile_picture_url,
        image_url=post.image_url,
        image_urls=post.image_urls or [],
        video_url=post.video_url,
        audio_url=post.audio_url,
        document_urls=post.document_urls or [],
        likes=post.likes or 0,
        shares=post.shares or 0,
        reposts=post.reposts or 0,
        saves=post.saves or 0,
        laughs=post.laughs or 0,
        replies_count=replies_counts.get(post.id, 0),
        quotes_count=quotes_counts.get(post.id, 0),
        slop_count=slop_counts.get(post.id, 0),
        liked_by_me=post.id in interactions["liked"],
        reposted_by_me=post.id in interactions["reposted"],
        is_followed_by_me=(post.user.id in followed_ids if current_user else False),
        is_saved_by_me=is_saved,
        laughed_by_me=post.id in interactions["laughed"],
        is_me=is_me,
        reposted_by=(repost_map or {}).get(post.id, []) if repost_map else None,
        media_metadata=post.media_metadata,
        quoted_post=build_quoted_post(post),
    )


def build_post_responses(
    posts: list[PostModel],
    current_user: User | None,
    db: Session,
    *,
    repost_map: dict | None = None,
    saved_override: bool | None = None,
) -> list[PostResponse]:
    """Batch-build PostResponse objects, avoiding N+1 queries (rule 21/64)."""
    if not posts:
        return []

    post_ids = [p.id for p in posts]
    replies_counts, quotes_counts = _batch_replies_and_quotes(post_ids, db)
    slop_counts = _batch_slop_counts(post_ids, db)
    interactions = _batch_interaction_ids(post_ids, current_user, db)
    followed_ids: set[int] = {u.id for u in current_user.followed} if current_user else set()

    return [
        _build_single_response(
            post,
            current_user=current_user,
            replies_counts=replies_counts,
            quotes_counts=quotes_counts,
            slop_counts=slop_counts,
            interactions=interactions,
            followed_ids=followed_ids,
            repost_map=repost_map,
            saved_override=saved_override,
        )
        for post in posts
    ]


# Backwards-compat re-export: external callers (profile/service.py) import
# `_build_post_responses`. Keep the old private name pointing at the public one.
_build_post_responses = build_post_responses
