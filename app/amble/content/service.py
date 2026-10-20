"""Business logic for Amble content retrieval (Phase 1.4b).

`next_posts_for_entity` resolves the binding for an entity_id, queries the
existing `posts.feeds.py` layer under a binding-appropriate filter, and
returns the next page. Cursor is a plain integer offset for now (client
sends it back, server just echoes it) — persistent server-side cursor
storage per user+entity is Phase 1.4d (`AmbleContentCursor` table).

CONTENT-01..06 mapping:
  - CONTENT-01: this function surfaces posts on demand
  - CONTENT-02: binding kind determines the query
  - CONTENT-03: blended bindings + hashtag matching keep the mapping loose
  - CONTENT-04: cursor advances per interaction
  - CONTENT-05: `empty=True` when no matching posts exist
  - CONTENT-06: PostResponse fields (id, author, text, timestamp) are mapped
"""

from __future__ import annotations

import logging
import operator
import time
from collections.abc import Sequence
from functools import reduce
from typing import Any

from sqlalchemy import ColumnElement, case, or_
from sqlalchemy.orm import Query, Session

from app.auth.models import User, followers
from app.common.utils import paginate
from app.posts.feeds import _base_feed_query
from app.posts.models import PostModel
from app.posts.schema import PostResponse
from app.posts.serializer import (
    _exclude_drafts_query,
    _exclude_slopped_query,
    build_post_responses,
)

from .bindings import get_binding
from .constants import (
    DEFAULT_PAGE_LIMIT,
    FOLLOW_BOOST_RANK,
    FRESHNESS_STALE_SECONDS,
    MAX_PAGE_LIMIT,
)
from .models import AmbleContentCursor
from .schema import (
    AmbleContentResponse,
    AmblePost,
    Binding,
    BlendedBinding,
    CategoryBinding,
    PersistentIdentityBinding,
)

logger = logging.getLogger(__name__)


class UnknownEntityError(Exception):
    """Entity id has no binding entry in `entity-bindings.yaml`. Views
    translate this to a 404."""


def parse_cursor(cursor: str | None) -> int:
    """Client-supplied cursor: integer offset serialised as its string form.
    Non-numeric input falls back to 0 — the client is always allowed to
    restart. Server-side persistence (Phase 1.4d) lives in
    `_load_cursor` / `_save_cursor` below; if the client doesn't send a
    cursor, we consult the DB, and after every fetch we persist the new
    offset there so it survives across sessions (D2)."""
    if not cursor:
        return 0
    try:
        parsed = int(cursor)
        return parsed if parsed >= 0 else 0
    except ValueError:
        return 0


def _load_cursor(db: Session, user_id: int, entity_id: str) -> int:
    """Read the persisted offset for (user, entity). Returns 0 when nothing
    is stored yet — the player has never interacted with this entity."""
    row = (
        db.query(AmbleContentCursor)
        .filter(
            AmbleContentCursor.user_id == user_id,
            AmbleContentCursor.entity_id == entity_id,
        )
        .one_or_none()
    )
    return row.offset_val if row is not None else 0


def _save_cursor(db: Session, user_id: int, entity_id: str, new_offset: int) -> None:
    """Upsert the offset for (user, entity). Uses a select + insert/update
    dance rather than a native UPSERT so this works across SQLite
    (test env) and Postgres (prod)."""
    row = (
        db.query(AmbleContentCursor)
        .filter(
            AmbleContentCursor.user_id == user_id,
            AmbleContentCursor.entity_id == entity_id,
        )
        .one_or_none()
    )
    if row is None:
        row = AmbleContentCursor(
            user_id=user_id,
            entity_id=entity_id,
            offset_val=new_offset,
        )
        db.add(row)
    else:
        row.offset_val = new_offset
    db.commit()


def _apply_binding_filter(
    query: Query[PostModel], binding: Binding, db: Session
) -> Query[PostModel]:
    """Return the query narrowed to only posts that match the binding."""
    if isinstance(binding, PersistentIdentityBinding):
        return _filter_by_usernames(query, binding.usernames, db)
    if isinstance(binding, CategoryBinding):
        return _filter_by_hashtags(query, binding.tags)
    if isinstance(binding, BlendedBinding):
        return _filter_by_any_part(query, binding, db)
    # Exhaustive by type — this line stays dead unless a new kind is added.
    raise ValueError(f"unknown binding kind: {type(binding).__name__}")


def _part_clause(
    part: PersistentIdentityBinding | CategoryBinding, db: Session
) -> ColumnElement[bool] | None:
    """SQL clause for one part of a blended binding, or None when that part
    can't match anything (unknown usernames, no tags)."""
    if isinstance(part, PersistentIdentityBinding):
        user_ids = _user_ids_for(part.usernames, db)
        return PostModel.user_id.in_(user_ids) if user_ids else None
    return _hashtag_clause(part.tags)


def _filter_by_any_part(
    query: Query[PostModel], binding: BlendedBinding, db: Session
) -> Query[PostModel]:
    """Blend by OR-ing every part's filter: the result is the union of all
    sources (weights inform ranking later, 1.4c+)."""
    part_clauses = (_part_clause(part, db) for part in binding.parts)
    clauses = [clause for clause in part_clauses if clause is not None]
    if not clauses:
        # Only unknown users / empty tags: force a no-match filter.
        return query.filter(False)
    return query.filter(or_(*clauses))


def _user_ids_for(usernames: Sequence[str], db: Session) -> list[int]:
    if not usernames:
        return []
    rows = db.query(User.id).filter(User.username.in_(list(usernames))).all()
    return [row.id for row in rows]


def _filter_by_usernames(
    query: Query[PostModel], usernames: Sequence[str], db: Session
) -> Query[PostModel]:
    user_ids = _user_ids_for(usernames, db)
    if not user_ids:
        return query.filter(False)
    return query.filter(PostModel.user_id.in_(user_ids))


def _hashtag_clause(tags: Sequence[str]) -> ColumnElement[bool] | None:
    """SQL clause matching posts whose text contains `#tag` for any tag.
    Case-insensitive LIKE. `posts.text` isn't indexed for substring search;
    for launch scale this is fine but if the category surface pattern
    grows we should add a Tag / PostTag table (see phases.md 1.4b note)."""
    if not tags:
        return None
    like_conditions = [PostModel.text.ilike(f"%#{tag}%") for tag in tags]
    return or_(*like_conditions) if like_conditions else None


def _filter_by_hashtags(query: Query[PostModel], tags: Sequence[str]) -> Query[PostModel]:
    clause = _hashtag_clause(tags)
    if clause is None:
        return query.filter(False)
    return query.filter(clause)


def _exclude_banned_authors_query(query: Query[PostModel]) -> Query[PostModel]:
    """Phase 2.3a — Skip posts whose author is banned. Joins User via the
    existing PostModel.user_id FK; a banned author's cells never surface
    in an amble anchor regardless of the binding pointing at them."""
    return query.join(User, PostModel.user_id == User.id).filter(User.is_banned.is_(False))


def _followed_user_ids(current_user: User | None, db: Session) -> list[int]:
    """Return the set of user_ids `current_user` follows. Empty when the
    viewer is anonymous or follows nobody."""
    if current_user is None:
        return []
    rows = (
        db.query(followers.c.followed_id)
        .filter(
            followers.c.follower_id == current_user.id,
        )
        .all()
    )
    return [row.followed_id for row in rows]


def _order_by_binding_options(
    query: Query[PostModel],
    entry_freshness_bias: float,
    followed_ids: Sequence[int],
) -> Query[PostModel]:
    """Phase 2.3b + 2.3c — apply freshness bias and follow-graph boost as
    ORDER BY clauses. Defaults collapse to the original recency ORDER BY
    so pre-2.3 anchors behave identically.

    Ranking key = follow_boost + effective_timestamp, sorted DESC.
      follow_boost   = FOLLOW_BOOST_RANK if author followed else 0
      effective_ts   = unix_timestamp when bias=0; unix_timestamp minus
                       an age penalty when bias > 0.
    """
    ranking_terms: list[ColumnElement[Any]] = []
    if followed_ids:
        ranking_terms.append(
            case((PostModel.user_id.in_(list(followed_ids)), FOLLOW_BOOST_RANK), else_=0)
        )
    if entry_freshness_bias > 0:
        now = int(time.time())
        # Penalty is bias * (age_seconds - staleness_threshold), clamped
        # ≥ 0 so fresh posts aren't down-ranked. Bigger bias = steeper
        # slope on old posts.
        age = now - PostModel.unix_timestamp
        ranking_terms.append(
            case(
                (
                    age > FRESHNESS_STALE_SECONDS,
                    PostModel.unix_timestamp
                    - (entry_freshness_bias * (age - FRESHNESS_STALE_SECONDS)),
                ),
                else_=PostModel.unix_timestamp,
            )
        )
    else:
        ranking_terms.append(PostModel.unix_timestamp)
    # Always at least one term (the timestamp), so no 0 start value is needed.
    return query.order_by(reduce(operator.add, ranking_terms).desc())


def _to_amble_post(post: PostResponse, source_id: int) -> AmblePost:
    """Map the rich internal PostResponse to the slim wire shape the amble
    dialogue frame renders (CONTENT-06 essentials + Phase 1.5 engagement)."""
    return AmblePost(
        id=source_id,
        author=post.username,
        text=post.text,
        unix_timestamp=post.unix_timestamp,
        likes=post.likes,
        reposts=post.reposts,
        saves=post.saves,
        liked_by_me=post.liked_by_me,
        reposted_by_me=bool(post.reposted_by_me),
    )


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_PAGE_LIMIT))


def _matching_posts_query(
    db: Session,
    current_user: User | None,
    binding: Binding,
    freshness_bias: float,
    personalise_by_follow: bool,
) -> Query[PostModel]:
    """The whole pipeline, shared by the live endpoint and the admin preview:
    posts the binding selects, minus what this viewer must not see (drafts,
    slopped posts, banned authors), in the binding's ranking order."""
    matching = _apply_binding_filter(_base_feed_query(db), binding, db)
    visible = _exclude_banned_authors_query(
        _exclude_slopped_query(_exclude_drafts_query(matching), current_user, db)
    )
    followed_ids = _followed_user_ids(current_user, db) if personalise_by_follow else []
    return _order_by_binding_options(
        visible, entry_freshness_bias=freshness_bias, followed_ids=followed_ids
    )


def _to_amble_posts(rows: list, current_user: User | None, db: Session) -> list[AmblePost]:
    responses = build_post_responses(rows, current_user, db)
    return [_to_amble_post(resp, row.id) for resp, row in zip(responses, rows, strict=True)]


def _empty_response(entity_id: str) -> AmbleContentResponse:
    """CONTENT-05 empty state: the binding exists but nothing matches."""
    return AmbleContentResponse(entity_id=entity_id, posts=[], next_cursor=None, empty=True)


def _starting_offset(
    db: Session, current_user: User | None, entity_id: str, cursor: str | None
) -> int:
    """D2: without a client cursor, resume from the cursor persisted for
    (user, entity). An explicit client cursor still wins, so the client can
    force a reset by sending "0"."""
    if cursor is None and current_user is not None:
        return _load_cursor(db, current_user.id, entity_id)
    return parse_cursor(cursor)


def next_posts_for_entity(
    db: Session,
    current_user: User | None,
    entity_id: str,
    cursor: str | None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> AmbleContentResponse:
    """Read the binding for `entity_id` and return the next page of posts.

    Raises `UnknownEntityError` when the entity has no binding entry —
    views translate to 404. When the binding exists but no posts match,
    returns `empty=True` so the frontend renders CONTENT-05.
    """
    entry = get_binding(entity_id, db=db)
    if entry is None:
        raise UnknownEntityError(entity_id)

    offset = _starting_offset(db, current_user, entity_id, cursor)
    query = _matching_posts_query(
        db, current_user, entry.binding, entry.freshness_bias, entry.personalise_by_follow
    )
    rows, has_more = paginate(query, offset, _clamp_limit(limit))
    if not rows:
        # Don't advance the persisted cursor: when posts appear later, the
        # player picks them up from the spot they left off.
        return _empty_response(entity_id)

    amble_posts = _to_amble_posts(rows, current_user, db)
    new_offset = offset + len(amble_posts)
    if current_user is not None:
        _save_cursor(db, current_user.id, entity_id, new_offset)
    return AmbleContentResponse(
        entity_id=entity_id,
        posts=amble_posts,
        next_cursor=str(new_offset) if has_more else None,
        empty=False,
    )


def preview_posts_for_binding(
    db: Session,
    current_user: User | None,
    entity_id: str,
    binding: Binding,
    limit: int = DEFAULT_PAGE_LIMIT,
    freshness_bias: float = 0.0,
    personalise_by_follow: bool = False,
) -> AmbleContentResponse:
    """Run the same filter pipeline as `next_posts_for_entity` against a
    caller-supplied binding, WITHOUT persisting a cursor or reading the
    DB override. Powers the Phase 2.2b admin preview panel — an admin
    picks a proposed binding and sees what posts would surface. Extended
    in 2.3 to accept the same freshness / personalise options so the
    preview matches what the endpoint would return.
    """
    query = _matching_posts_query(db, current_user, binding, freshness_bias, personalise_by_follow)
    rows, has_more = paginate(query, 0, _clamp_limit(limit))
    if not rows:
        return _empty_response(entity_id)
    amble_posts = _to_amble_posts(rows, current_user, db)
    return AmbleContentResponse(
        entity_id=entity_id,
        posts=amble_posts,
        next_cursor=str(len(amble_posts)) if has_more else None,
        empty=False,
    )
