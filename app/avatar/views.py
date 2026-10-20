"""Avatar API endpoints — deterministic preview and per-user regenerate."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.avatar.constants import MAX_PREVIEW_EMAIL_LEN, MAX_PREVIEW_USERNAME_LEN
from app.avatar.generator import generate_avatar, generate_avatar_url
from app.avatar.schema import AvatarUrlResponse
from app.common.auth_jwt import AuthJWT
from app.common.db import get_db
from app.common.utils import get_user

avatar_router = APIRouter()


@avatar_router.get(
    "/preview",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def preview_avatar(
    username: str = Query(..., min_length=1, max_length=MAX_PREVIEW_USERNAME_LEN),
    email: str = Query(..., min_length=1, max_length=MAX_PREVIEW_EMAIL_LEN),
) -> Response:
    """Preview an avatar without saving. Public endpoint for testing."""
    avatar_bytes = generate_avatar(username, email)
    return Response(content=avatar_bytes, media_type="image/png")


@avatar_router.post("/regenerate")
def regenerate_avatar(
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> AvatarUrlResponse:
    """Regenerate the current user's avatar from their identity hash."""
    Authorize.jwt_required()
    username = Authorize.get_jwt_subject()
    user = get_user(username, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    avatar_url = generate_avatar_url(username, user.email)
    user.profile_picture_url = avatar_url
    db.commit()
    return AvatarUrlResponse(url=avatar_url)
