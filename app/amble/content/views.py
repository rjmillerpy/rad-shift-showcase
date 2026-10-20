"""Amble content HTTP endpoints (Phase 1.4b, INT-01).

Only one endpoint for now — GET /amble/content/{entity_id}?cursor=... —
which the frontend hits every time the player opens the dialogue frame
for a content-backed entity. Auth is required so per-user cursor / slop
filtering behave correctly.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import required_user

from .constants import (
    ERROR_MESSAGE_UNKNOWN_ENTITY,
    LOG_EVENT_FETCH,
    LOG_EVENT_FETCH_UNKNOWN_ENTITY,
)
from .schema import AmbleContentResponse
from .service import UnknownEntityError, next_posts_for_entity

amble_content_router = APIRouter()
logger = logging.getLogger(__name__)


@amble_content_router.get("/{entity_id}", response_model=AmbleContentResponse)
def fetch_content(
    entity_id: str,
    cursor: str | None = Query(None),
    current_user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> AmbleContentResponse:
    try:
        response = next_posts_for_entity(db, current_user, entity_id, cursor)
    except UnknownEntityError:
        logger.info(
            LOG_EVENT_FETCH_UNKNOWN_ENTITY,
            extra={"entity_id": entity_id, "user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGE_UNKNOWN_ENTITY,
        ) from None  # deliberate translation of a domain error into a 404
    logger.info(
        LOG_EVENT_FETCH,
        extra={
            "entity_id": entity_id,
            "user_id": current_user.id,
            "post_count": len(response.posts),
            "empty": response.empty,
            "has_next": response.next_cursor is not None,
        },
    )
    return response
