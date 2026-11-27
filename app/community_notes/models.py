"""Community notes on posts, and the helpful / not-helpful ratings that score them."""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base

from .constants import MAX_SOURCE_URL_LENGTH, NoteStatus


class CommunityNote(Base):
    __tablename__ = "community_notes"
    # One note per author per post: a second one edits the first.
    __table_args__ = (UniqueConstraint("post_id", "author_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(MAX_SOURCE_URL_LENGTH), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)
    # Set by app/community_notes/scoring.py after each rating.
    status: Mapped[str] = mapped_column(
        String(32), default=NoteStatus.NEEDS_MORE_RATINGS.value, index=True
    )
    intercept: Mapped[float | None] = mapped_column(Float, nullable=True)
    factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Taken down by a moderator: hidden everywhere and left out of scoring.
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False)


class NoteRating(Base):
    __tablename__ = "community_note_ratings"

    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("community_notes.id", ondelete="CASCADE"), primary_key=True
    )
    rater_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    helpful: Mapped[bool] = mapped_column(Boolean)
    rated_at: Mapped[int] = mapped_column(Integer)
