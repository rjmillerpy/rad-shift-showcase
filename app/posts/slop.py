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

Readers choose how slop is ordered (slop_ordering): sunk (the default),
left in the feed's own order (sink_community_slop off, or slop_filter "show"
or "only", where sinking would fight the reader's choice), or floated to the
top worst first (slop_filter "all_slop", for readers who love pain).

Flags from before a moderator's dismissal (posts.slop_cleared_at) don't count.
"""

from sqlalchemy import Float, case, cast, false, func, or_
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

# How a ranked feed orders slop, from the reader's settings (slop_ordering).
SINK = "sink"  # below everything else
UNSORTED = "unsorted"  # wherever the feed's own score puts it
FLOAT = "float"  # on top, the sloppiest first
ALL_SLOP = "all_slop"  # the slop_filter choice that floats it
# slop_filter choices that already say what the reader wants to see of slop.
_FILTERS_WITHOUT_SINKING = ("show", "only")


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


def slop_ordering(settings: dict | None) -> str:
    settings = settings or {}
    slop_filter = settings.get("slop_filter")
    if slop_filter == ALL_SLOP:
        return FLOAT
    if slop_filter in _FILTERS_WITHOUT_SINKING or not settings.get("sink_community_slop", True):
        return UNSORTED
    return SINK


def rank_key(flags_column, ordering: str, ai_content: str):
    """Sorted ascending ahead of a feed's own score: where slop goes.

    "less" sinks AI-labelled posts in every ordering but FLOAT, where only
    slop counts.
    """
    if ordering == FLOAT:
        return -slop_score(flags_column)
    sinks = slop_score(flags_column) >= DEMOTE_AT if ordering == SINK else false()
    if ai_content == AI_LESS:
        sinks = or_(sinks, PostModel.ai_label.is_not(None))
    return case((sinks, 1), else_=0)


def ai_content_setting(settings: dict | None) -> str:
    choice = (settings or {}).get("ai_content", AI_SHOW)
    return choice if choice in AI_CONTENT_CHOICES else AI_SHOW


def apply_ai_setting(query: Query[PostModel], ai_content: str) -> Query[PostModel]:
    """Drop AI-labelled posts for readers who chose to hide them."""
    if ai_content == AI_HIDE:
        return query.filter(PostModel.ai_label.is_(None))
    return query


def rank_keys(post_ids: list[int], ordering: str, ai_content: str, db: Session) -> dict[int, float]:
    """rank_key per post, for feeds ranked in Python (trending)."""
    if not post_ids:
        return {}
    flags = counted_flags(db)
    rows = (
        db.query(PostModel.id, rank_key(flags.c.flags, ordering, ai_content))
        .outerjoin(flags, flags.c.post_id == PostModel.id)
        .filter(PostModel.id.in_(post_ids))
    )
    return {int(post_id): float(key) for post_id, key in rows.all()}
