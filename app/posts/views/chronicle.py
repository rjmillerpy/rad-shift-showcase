"""Chronicle endpoints — thin wrappers around app.chronicle.service."""

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.auth.models import User
from app.chronicle.constants import (
    CHRONICLE_DEFAULT_POSTS_PER_PAGE,
    CHRONICLE_MAX_POSTS_PER_PAGE,
)
from app.chronicle.service import generate_chronicle, stream_chronicle
from app.common.auth_jwt import AuthJWT, AuthJWTException
from app.common.db import SessionLocal, get_db
from app.common.deps import optional_user
from app.common.utils import get_user

from ..schema import ChronicleResponse

router = APIRouter()


PageQuery = Query(0, ge=0)
PostsPerPageQuery = Query(
    CHRONICLE_DEFAULT_POSTS_PER_PAGE,
    ge=1,
    le=CHRONICLE_MAX_POSTS_PER_PAGE,
)


@router.get("/chronicle", response_model_exclude_unset=True)
def get_chronicle(
    page: int = PageQuery,
    posts_per_page: int = PostsPerPageQuery,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ChronicleResponse:
    return ChronicleResponse.model_validate(
        generate_chronicle(
            db=db,
            current_user=current_user,
            page=page,
            posts_per_page=posts_per_page,
        )
    )


def _resolve_username_from_token(token: str | None) -> str | None:
    """Extract the subject from an SSE query-param token.

    The stream endpoint takes the JWT as `?token=` because SSE from the browser
    can't set custom headers. Silence on AuthJWTException is intentional —
    unauthenticated stream access is supported.
    """
    if not token:
        return None
    try:
        sub = AuthJWT().get_raw_jwt(token).get("sub")
    except AuthJWTException:
        return None
    return sub if isinstance(sub, str) else None


@router.get(
    "/chronicle/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def get_chronicle_stream(
    page: int = PageQuery,
    posts_per_page: int = PostsPerPageQuery,
    token: str | None = None,
) -> StreamingResponse:
    username = _resolve_username_from_token(token)

    def event_generator() -> Iterator[str]:
        db = SessionLocal()
        try:
            current_user = get_user(username, db) if username else None
            for chunk in stream_chronicle(
                db=db,
                current_user=current_user,
                page=page,
                posts_per_page=posts_per_page,
            ):
                yield f"data: {chunk}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
