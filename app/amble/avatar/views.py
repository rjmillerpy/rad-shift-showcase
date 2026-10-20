"""Amble avatar HTTP endpoints (rule 39 — controllers convert domain errors
to HTTP responses; they don't re-implement business logic)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import required_user

from .constants import (
    ERROR_MESSAGE_PERSISTENCE,
    LOG_EVENT_READ,
    LOG_EVENT_UPSERT,
)
from .schema import AvatarResponse, AvatarUpdateRequest
from .service import (
    AvatarPersistenceError,
    get_avatar_for_user,
    upsert_avatar_for_user,
)

amble_avatar_router = APIRouter()
logger = logging.getLogger(__name__)


@amble_avatar_router.get("", response_model=AvatarResponse)
def read_avatar(
    current_user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> AvatarResponse:
    avatar = get_avatar_for_user(db, current_user.id)
    logger.info(
        LOG_EVENT_READ,
        extra={"user_id": current_user.id, "has_avatar": avatar is not None},
    )
    return AvatarResponse(avatar=avatar, exists=avatar is not None)


@amble_avatar_router.put("", response_model=AvatarResponse)
def upsert_avatar(
    body: AvatarUpdateRequest,
    current_user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> AvatarResponse:
    try:
        saved = upsert_avatar_for_user(db, current_user.id, body.avatar)
    except AvatarPersistenceError as cause:
        logger.error(
            "amble.avatar.upsert.error",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGE_PERSISTENCE,
        ) from cause
    logger.info(LOG_EVENT_UPSERT, extra={"user_id": current_user.id})
    return AvatarResponse(avatar=saved, exists=True)
