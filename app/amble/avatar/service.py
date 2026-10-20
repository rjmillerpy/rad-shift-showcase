"""Business logic for the Amble avatar sub-domain.

Only three public actions: read the current user's avatar, upsert it, and a
domain error the views translate to a 500. Repositories aren't broken out
separately at this scale — SQLAlchemy queries live here directly. If a
second amble sub-domain ends up sharing DB access patterns we'll extract at
that point (rule 20 — no anticipatory extraction).
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .constants import ERROR_MESSAGE_PERSISTENCE, LOG_EVENT_UPSERT_FAILED
from .models import AmbleAvatar
from .schema import AvatarSchema

logger = logging.getLogger(__name__)


class AvatarPersistenceError(Exception):
    """Domain-level failure the views translate to a 500. Wraps SQLAlchemy
    errors so we never leak DB internals to clients (rule 10, rule 36)."""


def get_avatar_for_user(db: Session, user_id: int) -> AvatarSchema | None:
    row = db.query(AmbleAvatar).filter(AmbleAvatar.user_id == user_id).one_or_none()
    if row is None:
        return None
    return AvatarSchema.model_validate(row.config)


def upsert_avatar_for_user(
    db: Session,
    user_id: int,
    avatar: AvatarSchema,
) -> AvatarSchema:
    payload = avatar.model_dump()
    row = db.query(AmbleAvatar).filter(AmbleAvatar.user_id == user_id).one_or_none()
    try:
        if row is None:
            row = AmbleAvatar(user_id=user_id, config=payload)
            db.add(row)
        else:
            row.config = payload
        db.commit()
    except SQLAlchemyError as cause:
        db.rollback()
        logger.exception(LOG_EVENT_UPSERT_FAILED, extra={"user_id": user_id})
        raise AvatarPersistenceError(ERROR_MESSAGE_PERSISTENCE) from cause
    return avatar
