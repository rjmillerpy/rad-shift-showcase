"""SQLAlchemy model for the per-user Amble avatar.

The avatar payload is stored as a JSON blob so we can evolve the per-half
attribute set (adding accessories in a later phase, for example) without
adding columns. The Pydantic schema is the source of truth for the JSON
shape and is validated on the boundary in service.py (rule 5).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)

from app.common.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AmbleAvatar(Base):
    __tablename__ = "amble_avatars"
    __table_args__ = (UniqueConstraint("user_id", name="uq_amble_avatars_user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
