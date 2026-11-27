"""What the admin dashboard shows: traffic, and engagement by feed mode and content source.

Phase 3's gate: "engagement per feed mode and per content source is visible
on a dashboard". A mode's engagement rate is its engagements per page view,
so a mode with few readers who engage a lot stands out from a busy one
nobody interacts with.
"""

from dataclasses import dataclass

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from .constants import DAY_SECONDS, EventType
from .models import AnalyticsEvent

TOP_PAGES = 10


@dataclass(frozen=True)
class Traffic:
    days: list[dict]  # day (unix seconds), views, visitors
    top_pages: list[dict]  # path, views
    by_mode: list[dict]  # mode, views, visitors, engagements, engagement_rate
    by_source: list[dict]  # source, engagements, posts


def traffic_since(since_unix: int, db: Session) -> Traffic:
    first_day = since_unix // DAY_SECONDS
    views = db.query(AnalyticsEvent).filter(
        AnalyticsEvent.day >= first_day, AnalyticsEvent.event_type == EventType.PAGE_VIEW.value
    )
    engagements = db.query(AnalyticsEvent).filter(
        AnalyticsEvent.day >= first_day, AnalyticsEvent.event_type == EventType.ENGAGEMENT.value
    )
    return Traffic(
        days=_days(views),
        top_pages=_top_pages(views),
        by_mode=_by_mode(views, engagements),
        by_source=_by_source(engagements),
    )


def _days(views) -> list[dict]:
    rows = (
        views.with_entities(
            AnalyticsEvent.day,
            func.count(AnalyticsEvent.id),
            func.count(distinct(AnalyticsEvent.visitor)),
        )
        .group_by(AnalyticsEvent.day)
        .order_by(AnalyticsEvent.day)
        .all()
    )
    return [
        {"day": day * DAY_SECONDS, "views": count, "visitors": visitors}
        for day, count, visitors in rows
    ]


def _top_pages(views) -> list[dict]:
    count = func.count(AnalyticsEvent.id)
    rows = (
        views.with_entities(AnalyticsEvent.path, count)
        .group_by(AnalyticsEvent.path)
        .order_by(count.desc(), AnalyticsEvent.path)
        .limit(TOP_PAGES)
        .all()
    )
    return [{"path": path, "views": n} for path, n in rows]


def _by_mode(views, engagements) -> list[dict]:
    seen = {
        mode: (n, visitors)
        for mode, n, visitors in views.filter(AnalyticsEvent.mode.is_not(None))
        .with_entities(
            AnalyticsEvent.mode,
            func.count(AnalyticsEvent.id),
            func.count(distinct(AnalyticsEvent.visitor)),
        )
        .group_by(AnalyticsEvent.mode)
        .all()
    }
    engaged = dict(
        engagements.filter(AnalyticsEvent.mode.is_not(None))
        .with_entities(AnalyticsEvent.mode, func.count(AnalyticsEvent.id))
        .group_by(AnalyticsEvent.mode)
        .all()
    )
    rows = []
    for mode in sorted(set(seen) | set(engaged)):
        n_views, visitors = seen.get(mode, (0, 0))
        n_engaged = engaged.get(mode, 0)
        rows.append(
            {
                "mode": mode,
                "views": n_views,
                "visitors": visitors,
                "engagements": n_engaged,
                # None, not infinity, for engagement with no recorded views.
                "engagement_rate": round(n_engaged / n_views, 3) if n_views else None,
            }
        )
    return sorted(rows, key=lambda row: (-row["views"], row["mode"]))


def _by_source(engagements) -> list[dict]:
    rows = (
        engagements.with_entities(
            AnalyticsEvent.source,
            func.count(AnalyticsEvent.id),
            func.count(distinct(AnalyticsEvent.post_id)),
        )
        .group_by(AnalyticsEvent.source)
        .order_by(AnalyticsEvent.source)
        .all()
    )
    return [{"source": source, "engagements": n, "posts": posts} for source, n, posts in rows]
