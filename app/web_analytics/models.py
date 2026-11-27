"""Analytics events and the daily salts that anonymise visitors."""

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (Index("ix_analytics_events_day_type", "day", "event_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[int] = mapped_column(Integer)
    # Unix day (occurred_at // 86400): every report groups by it.
    day: Mapped[int] = mapped_column(Integer)
    visitor: Mapped[str] = mapped_column(String(16))
    event_type: Mapped[str] = mapped_column(String(20))
    path: Mapped[str | None] = mapped_column(String(200))
    mode: Mapped[str | None] = mapped_column(String(20), index=True)
    # Engagements only: what was done, to which post, and where the post came from.
    action: Mapped[str | None] = mapped_column(String(20))
    post_id: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(20))


class VisitorSalt(Base):
    """One random salt per day; deleted after two, which makes old hashes unlinkable."""

    __tablename__ = "analytics_salts"

    day: Mapped[int] = mapped_column(Integer, primary_key=True)
    salt: Mapped[str] = mapped_column(String(64))
