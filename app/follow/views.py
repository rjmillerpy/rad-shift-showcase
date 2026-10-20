"""Follow / unfollow API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.auth.constants import MAX_USERNAME_LEN
from app.auth.models import User
from app.common.auth_jwt import AuthJWT
from app.common.db import get_db
from app.common.schema import MessageResponse
from app.common.utils import get_user, require_verified
from app.follow.service import follow_user, is_following, unfollow_user

logger = logging.getLogger(__name__)


follow_router = APIRouter()


UsernamePath = Path(..., min_length=1, max_length=MAX_USERNAME_LEN)


def _resolve_follow_target(
    username: str,
    Authorize: AuthJWT,
    db: Session,
) -> tuple[User, User]:
    """Resolve (current_user, target_user) and enforce shared preconditions.

    Raises 401 if unauthenticated, 403 if unverified, 404 if the target is gone.
    """
    Authorize.jwt_required()
    current = get_user(Authorize.get_jwt_subject(), db)
    if current is None:
        raise HTTPException(status_code=404, detail="User not found")
    require_verified(current)
    target = get_user(username, db)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    return current, target


@follow_router.post("/{username}")
def follow(
    username: str = UsernamePath,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> MessageResponse:
    current, target = _resolve_follow_target(username, Authorize, db)
    if target.id == current.id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")
    if is_following(current.id, target.id, db):
        raise HTTPException(status_code=400, detail="Already following this user")
    follow_user(current, target, db)
    logger.info("User %s followed %s", current.id, target.id)
    return MessageResponse(message=f"You are now following {username}")


@follow_router.post("/un/{username}")
def unfollow(
    username: str = UsernamePath,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> MessageResponse:
    current, target = _resolve_follow_target(username, Authorize, db)
    if not is_following(current.id, target.id, db):
        raise HTTPException(status_code=400, detail="You are not following this user")
    unfollow_user(current, target, db)
    logger.info("User %s unfollowed %s", current.id, target.id)
    return MessageResponse(message=f"You have unfollowed {username}")
