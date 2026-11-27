"""Slop ranking: posts the community calls slop sink below the rest of a ranked feed.

A post's slop score is the share of its reactions that are slop flags,
smoothed toward a small prior so a handful of flags on a new post can't
sink it:

    score = (flags + PRIOR × PSEUDO_COUNT) / (flags + positive reactions + PSEUDO_COUNT)

One flag on a new post scores 0.21; three flags and no likes 0.41
(demoted); three flags on a post with 50 likes 0.06. A share, not a
count, so three coordinated accounts can't bury a popular post, and a viral
post can't outrun a wave of flags just by being viral.

Demotion is a sort key ahead of the feed's own score, not a number mixed
into it: the feed's score adds engagement counts to a recency term in other
units, where any fixed penalty is either nothing or years.

Flags from before a moderator's dismissal (posts.slop_cleared_at) don't count.
"""

from sqlalchemy import Float, and_, case, cast, func
from sqlalchemy.orm import Query, Session

from .models import PostModel, Slop

PRIOR = 0.05
PSEUDO_COUNT = 5
DEMOTE_AT = 0.3

# The user setting for AI-labelled posts (algo_settings["ai_content"]).
AI_SHOW = "show"
AI_LESS = "less"  # sink them like slop
AI_HIDE = "hide"
AI_CONTENT_CHOICES = (AI_SHOW, AI_LESS, AI_HIDE)


def counted_flags(db: Session):
    """Per post: slop flags made since its last moderator dismissal (a subquery)."""
    return (
        db.query(Slop.post_id.label("post_id"), func.count(Slop.id).label("flags"))
        .join(PostModel, PostModel.id == Slop.post_id)
        .filter(Slop.unix_timestamp > func.coalesce(PostModel.slop_cleared_at, 0))
        .group_by(Slop.post_id)
        .subquery()
    )


def positive_reactions():
    return (
        func.coalesce(PostModel.likes, 0)
        + func.coalesce(PostModel.laughs, 0)
        + func.coalesce(PostModel.reposts, 0)
        + func.coalesce(PostModel.saves, 0)
        + func.coalesce(PostModel.shares, 0)
    )


def slop_score(flags_column):
    flags = cast(func.coalesce(flags_column, 0), Float)
    return (flags + PRIOR * PSEUDO_COUNT) / (flags + positive_reactions() + PSEUDO_COUNT)


def demoted(flags_column, ai_content: str):
    """1 for a post that sinks below the rest (slop, or AI-labelled for "less"), else 0."""
    sinks = slop_score(flags_column) >= DEMOTE_AT
    if ai_content == AI_LESS:
        sinks = sinks | PostModel.ai_label.is_not(None)
    return case((sinks, 1), else_=0)


def ai_content_setting(settings: dict | None) -> str:
    choice = (settings or {}).get("ai_content", AI_SHOW)
    return choice if choice in AI_CONTENT_CHOICES else AI_SHOW


def apply_ai_setting(query: Query[PostModel], ai_content: str) -> Query[PostModel]:
    """Drop AI-labelled posts for readers who chose to hide them."""
    if ai_content == AI_HIDE:
        return query.filter(PostModel.ai_label.is_(None))
    return query


def demoted_ids(post_ids: list[int], ai_content: str, db: Session) -> set[int]:
    """Which of these posts sink (for feeds ranked in Python, like trending)."""
    if not post_ids:
        return set()
    flags = counted_flags(db)
    query: Query[tuple[int]] = (
        db.query(PostModel.id)
        .outerjoin(flags, flags.c.post_id == PostModel.id)
        .filter(and_(PostModel.id.in_(post_ids), demoted(flags.c.flags, ai_content) == 1))
    )
    return {int(post_id) for (post_id,) in query.all()}
