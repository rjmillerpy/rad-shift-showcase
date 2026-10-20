"""Toggle endpoints: like / laugh / repost / share / save / slop."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import optional_user, verified_user

from ..schema import (
    LaughToggleResponse,
    LikeToggleResponse,
    PostStatusResponse,
    RepostToggleResponse,
    SaveToggleResponse,
    ShareResponse,
    SlopRequest,
)
from ..toggles import (
    mark_post_slop,
    share_post,
    toggle_laugh,
    toggle_like,
    toggle_repost,
    toggle_save,
)

router = APIRouter()


@router.post("/like/{post_id}")
def toggle_post_like(
    post_id: int,
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> LikeToggleResponse:
    return LikeToggleResponse.model_validate(toggle_like(post_id, user, db))


@router.post("/laugh/{post_id}")
def toggle_post_laugh(
    post_id: int,
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> LaughToggleResponse:
    return LaughToggleResponse.model_validate(toggle_laugh(post_id, user, db))


@router.post("/repost/{post_id}")
def repost(
    post_id: int,
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> RepostToggleResponse:
    return RepostToggleResponse.model_validate(toggle_repost(post_id, user, db))


@router.post("/share/{post_id}")
def share(
    post_id: int,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ShareResponse:
    return ShareResponse.model_validate(share_post(post_id, current_user, db))


@router.post("/save/{post_id}")
def save_toggle(
    post_id: int,
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> SaveToggleResponse:
    return SaveToggleResponse.model_validate(toggle_save(post_id, user, db))


@router.post("/slop/{post_id}")
def mark_slop(
    post_id: int,
    payload: SlopRequest,
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> PostStatusResponse:
    return PostStatusResponse.model_validate(mark_post_slop(post_id, user, payload.reason, db))
