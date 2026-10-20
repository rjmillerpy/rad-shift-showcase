"""Feed queries — every "list N posts filtered / ordered by X" path."""

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Query, Session, joinedload

from app.auth.models import User
from app.common.utils import paginate

from .constants import MEDIA_TYPE_FILTERS
from .models import PostModel, PostSave, Repost, Slop
from .schema import PostResponse
from .serializer import (
    _exclude_drafts_query,
    _exclude_slopped_query,
    build_post_responses,
    get_ordered_model,
)

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
    return (
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
    base_query = db.query(PostModel).filter(
        PostModel.parent_post_id == parent_post_id,
        PostModel.is_reply == True,  # noqa: E712
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


def _algo_score_query(db: Session, weights: AlgoWeights) -> Query[PostModel]:
    """Return the base feed query ordered by the weighted engagement score."""
    slop_count_sq = (
        db.query(Slop.post_id, func.count(Slop.id).label("cnt")).group_by(Slop.post_id).subquery()
    )
    engagement = (
        func.coalesce(PostModel.likes, 0) * weights.like
        + func.coalesce(PostModel.reposts, 0) * weights.repost
        + func.coalesce(PostModel.shares, 0) * weights.share
        + func.coalesce(PostModel.laughs, 0) * weights.laugh
        + func.coalesce(PostModel.saves, 0) * weights.save
        - func.coalesce(slop_count_sq.c.cnt, 0) * weights.slop
    )
    recency_score = (
        func.coalesce(PostModel.unix_timestamp, 0) / _RECENCY_TIMESTAMP_DIVISOR * weights.recency
    )
    score = engagement + recency_score

    return (
        db.query(PostModel)
        .outerjoin(slop_count_sq, PostModel.id == slop_count_sq.c.post_id)
        .options(joinedload(PostModel.user), joinedload(PostModel.parent_post))
        .filter(PostModel.is_reply == False)  # noqa: E712
        .order_by(score.desc(), PostModel.unix_timestamp.desc())
    )


def get_algo_posts_formatted(
    db: Session,
    current_user: User | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PostResponse], bool]:
    """Algorithmic feed with configurable weights from user settings."""
    settings: dict = (
        current_user.algo_settings if current_user and current_user.algo_settings else {}
    )
    if settings.get("engagement_enabled", True):
        base_query = _algo_score_query(db, AlgoWeights.from_settings(settings))
    else:
        base_query = _base_feed_query(db).order_by(PostModel.unix_timestamp.desc())

    filtered = _exclude_slopped_query(_exclude_drafts_query(base_query), current_user, db)
    posts, has_more = paginate(filtered, offset, limit)
    return build_post_responses(posts, current_user, db), has_more


def get_single_post_formatted(
    post_id: int,
    db: Session,
    current_user: User | None = None,
) -> PostResponse | None:
    post = (
        db.query(PostModel)
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
        db.query(PostModel)
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
