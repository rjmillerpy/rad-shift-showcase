"""Feed queries — every "list N posts filtered / ordered by X" path."""

import time
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Query, Session, joinedload

from app.auth.models import User
from app.common.utils import paginate
from app.engagement.trending import ranked_post_ids

from .constants import MEDIA_TYPE_FILTERS
from .models import PostModel, PostSave, Repost
from .schema import PostResponse
from .serializer import (
    _exclude_drafts_query,
    _exclude_slopped_query,
    build_post_responses,
    by_active_authors,
    get_ordered_model,
)
from .slop import (
    ai_content_setting,
    apply_ai_setting,
    counted_flags,
    rank_key,
    rank_keys,
    slop_ordering,
)
from .tailoring import Tailoring, boost, diversify, filter_posts, reader_settings

# Recency multiplier used when translating a unix-timestamp column into a
# score contribution comparable to engagement counts.
_RECENCY_TIMESTAMP_DIVISOR = 100_000.0


@dataclass(frozen=True)
class AlgoWeights:
    """Per-user weights applied to the algorithmic feed's ranking formula.

    Parsed once from `user.algo_settings` at query time. Keeping this as a
    typed value object (rule 43 — extract complex boolean/arithmetic into
    named variables) makes the ranking arithmetic in `_algo_score_query`
    readable and lets the tests instantiate weights directly.
    """

    like: float = 1.0
    repost: float = 1.0
    share: float = 1.0
    laugh: float = 0.5
    save: float = 0.5
    slop: float = 0.0
    recency: float = 0.3

    @classmethod
    def from_settings(cls, settings: dict | None) -> "AlgoWeights":
        s = settings or {}
        return cls(
            like=float(s.get("like_weight", cls.like)),
            repost=float(s.get("repost_weight", cls.repost)),
            share=float(s.get("share_weight", cls.share)),
            laugh=float(s.get("laugh_weight", cls.laugh)),
            save=float(s.get("save_weight", cls.save)),
            slop=float(s.get("slop_weight", cls.slop)),
            recency=float(s.get("recency_weight", cls.recency)),
        )


def _base_feed_query(db: Session) -> Query[PostModel]:
    return by_active_authors(
        db.query(PostModel)
        .options(joinedload(PostModel.user), joinedload(PostModel.parent_post))
        .filter(PostModel.is_reply == False)  # noqa: E712
    )


def get_replies_formatted(
    parent_post_id: int,
    db: Session,
    current_user: User | None = None,
    desc: bool = True,
) -> list[PostResponse]:
    base_query = by_active_authors(
        db.query(PostModel).filter(
            PostModel.parent_post_id == parent_post_id,
            PostModel.is_reply == True,  # noqa: E712
        )
    )
    drafts_excluded = _exclude_drafts_query(base_query)
    replies = (
        _exclude_slopped_query(drafts_excluded, current_user, db)
        .order_by(get_ordered_model(desc))
        .all()
    )
    return build_post_responses(replies, current_user, db)


def get_all_posts_formatted(
    db: Session,
    current_user: User | None = None,
    desc: bool = True,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PostResponse], bool]:
    base_query = _base_feed_query(db).order_by(get_ordered_model(desc))
    filtered = _exclude_slopped_query(_exclude_drafts_query(base_query), current_user, db)
    posts, has_more = paginate(filtered, offset, limit)
    return build_post_responses(posts, current_user, db), has_more


def get_media_posts_formatted(
    db: Session,
    current_user: User | None = None,
    media_type: str = "all",
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PostResponse], bool]:
    """Return posts with audio/video, optionally filtered by media type."""
    base_query = _base_feed_query(db).order_by(PostModel.unix_timestamp.desc())
    media_filter = MEDIA_TYPE_FILTERS.get(media_type, MEDIA_TYPE_FILTERS["all"])
    base_query = media_filter(base_query)
    filtered = _exclude_slopped_query(_exclude_drafts_query(base_query), current_user, db)
    posts, has_more = paginate(filtered, offset, limit)
    return build_post_responses(posts, current_user, db), has_more


def _repost_map_for_followed(
    followed_users: list,
    db: Session,
) -> tuple[dict, list[int]]:
    followed_ids = [u.id for u in followed_users]
    reposts = db.query(Repost).filter(Repost.user_id.in_(followed_ids)).all()
    user_map = {u.id: u.username for u in followed_users}
    repost_map: dict[int, list[str]] = {}
    reposted_post_ids: list[int] = []
    for r in reposts:
        username = user_map.get(r.user_id)
        if not username:
            continue
        reposted_post_ids.append(r.original_post_id)
        repost_map.setdefault(r.original_post_id, []).append(username)
    return repost_map, reposted_post_ids


def get_followed_posts_formatted(
    current_user: User,
    db: Session,
    desc: bool = True,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PostResponse], bool]:
    followed_users = current_user.followed
    followed_ids = [u.id for u in followed_users]
    repost_map, reposted_post_ids = _repost_map_for_followed(followed_users, db)

    base_query = (
        _base_feed_query(db)
        .filter(PostModel.user_id.in_(followed_ids) | PostModel.id.in_(reposted_post_ids))
        .order_by(get_ordered_model(desc))
    )
    filtered = _exclude_slopped_query(_exclude_drafts_query(base_query), current_user, db)
    posts, has_more = paginate(filtered, offset, limit)
    return build_post_responses(posts, current_user, db, repost_map=repost_map), has_more


def _algo_score_query(
    db: Session, weights: AlgoWeights, settings: dict, viewer: User | None
) -> Query[PostModel]:
    """The base feed query: slop placed per app/posts/slop.py, then the tailored score."""
    flags = counted_flags(db)
    positive_engagement = (
        func.coalesce(PostModel.likes, 0) * weights.like
        + func.coalesce(PostModel.reposts, 0) * weights.repost
        + func.coalesce(PostModel.shares, 0) * weights.share
        + func.coalesce(PostModel.laughs, 0) * weights.laugh
        + func.coalesce(PostModel.saves, 0) * weights.save
    )
    engagement = positive_engagement - func.coalesce(flags.c.flags, 0) * weights.slop
    recency_score = (
        func.coalesce(PostModel.unix_timestamp, 0) / _RECENCY_TIMESTAMP_DIVISOR * weights.recency
    )
    tailored = boost(Tailoring.from_settings(settings), viewer, positive_engagement, db)
    score = engagement + recency_score + tailored

    return by_active_authors(
        db.query(PostModel)
        .outerjoin(flags, PostModel.id == flags.c.post_id)
        .options(joinedload(PostModel.user), joinedload(PostModel.parent_post))
        .filter(PostModel.is_reply == False)  # noqa: E712
    ).order_by(
        _slop_key(flags.c.flags, settings).asc(), score.desc(), PostModel.unix_timestamp.desc()
    )


def _chronological_query(db: Session, settings: dict) -> Query[PostModel]:
    """Engagement ranking off: newest first, with slop still placed per the reader's choice."""
    flags = counted_flags(db)
    return (
        _base_feed_query(db)
        .outerjoin(flags, PostModel.id == flags.c.post_id)
        .order_by(_slop_key(flags.c.flags, settings).asc(), PostModel.unix_timestamp.desc())
    )


def _slop_key(flags_column, settings: dict):
    return rank_key(flags_column, slop_ordering(settings), ai_content_setting(settings))


def get_algo_posts_formatted(
    db: Session,
    current_user: User | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PostResponse], bool]:
    """Algorithmic feed with configurable weights from user settings."""
    settings = reader_settings(current_user)
    ai_content = ai_content_setting(settings)
    tailoring = Tailoring.from_settings(settings)
    if settings.get("engagement_enabled", True):
        weights = AlgoWeights.from_settings(settings)
        base_query = _algo_score_query(db, weights, settings, current_user)
    else:
        base_query = _chronological_query(db, settings)

    filtered = filter_posts(
        apply_ai_setting(
            _exclude_slopped_query(_exclude_drafts_query(base_query), current_user, db),
            ai_content,
        ),
        tailoring,
        current_user,
        db,
    )
    posts, has_more = paginate(filtered, offset, limit)
    posts = diversify(posts, tailoring.diversity, db)
    return build_post_responses(posts, current_user, db), has_more


def get_trending_posts_formatted(
    db: Session,
    current_user: User | None = None,
    offset: int = 0,
    limit: int = 20,
    now: float | None = None,
) -> tuple[list[PostResponse], bool]:
    """Posts with the most engagement lately, from the Kafka-fed scores (app/engagement/).

    Ranked in Python (the scores decay with time); drafts, replies and the
    viewer's slop-marked posts are filtered out before paging, and slop is
    placed per the viewer's choice (app/posts/slop.py).
    """
    ranked = ranked_post_ids(db, time.time() if now is None else now)
    if not ranked:
        return [], False
    settings = reader_settings(current_user)
    ai_content = ai_content_setting(settings)
    visible = filter_posts(
        apply_ai_setting(
            _exclude_slopped_query(
                _exclude_drafts_query(_base_feed_query(db).filter(PostModel.id.in_(ranked))),
                current_user,
                db,
            ),
            ai_content,
        ),
        Tailoring.from_settings(settings),
        current_user,
        db,
    ).all()
    rank = {post_id: position for position, post_id in enumerate(ranked)}
    keys = rank_keys([post.id for post in visible], slop_ordering(settings), ai_content, db)
    ordered = sorted(visible, key=lambda post: (keys[post.id], rank[post.id]))
    page = ordered[offset : offset + limit]
    return build_post_responses(page, current_user, db), len(ordered) > offset + limit


def get_single_post_formatted(
    post_id: int,
    db: Session,
    current_user: User | None = None,
) -> PostResponse | None:
    post = (
        by_active_authors(db.query(PostModel))
        .options(joinedload(PostModel.user), joinedload(PostModel.parent_post))
        .filter(PostModel.id == post_id)
        .first()
    )
    if not post:
        return None
    results = build_post_responses([post], current_user, db)
    return results[0] if results else None


def get_saved_posts_formatted(
    current_user: User,
    db: Session,
    desc: bool = True,
) -> list[PostResponse]:
    saved = db.query(PostSave).filter_by(user_id=current_user.id).all()
    post_ids = [s.post_id for s in saved]
    if not post_ids:
        return []
    posts = (
        by_active_authors(db.query(PostModel))
        .options(joinedload(PostModel.user), joinedload(PostModel.parent_post))
        .filter(PostModel.id.in_(post_ids))
        .filter(PostModel.is_draft == False)  # noqa: E712
        .order_by(get_ordered_model(desc))
        .all()
    )
    return build_post_responses(posts, current_user, db, saved_override=True)


def get_user_drafts_formatted(
    current_user: User,
    db: Session,
    desc: bool = True,
) -> list[PostResponse]:
    posts = (
        db.query(PostModel)
        .options(joinedload(PostModel.user), joinedload(PostModel.parent_post))
        .filter(
            PostModel.user_id == current_user.id,
            PostModel.is_draft == True,  # noqa: E712
        )
        .order_by(get_ordered_model(desc))
        .all()
    )
    return build_post_responses(posts, current_user, db)
