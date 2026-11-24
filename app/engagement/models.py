"""Tables the engagement aggregator writes (app/engagement/aggregator.py)."""

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class PostTrending(Base):
    """A post's trending score as of `updated_at` (it halves every 6 hours from there)."""

    __tablename__ = "post_trending"

    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # Unix seconds of the newest event folded into the score.
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)


class ProcessedPostEvent(Base):
    """Event ids already applied, so a redelivered event changes nothing."""

    __tablename__ = "processed_post_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)
