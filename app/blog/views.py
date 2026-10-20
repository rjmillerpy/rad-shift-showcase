"""Blog post API endpoints."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.auth.models import User
from app.blog.constants import (
    DEFAULT_LIST_LIMIT,
    IP_HASH_LEN,
    MAX_LIST_LIMIT,
    MAX_USERNAME_FILTER_LEN,
)
from app.blog.models import BlogPost
from app.blog.schema import (
    BlogCreateRequest,
    BlogDraftsResponse,
    BlogListResponse,
    BlogPostResponse,
    BlogStatsResponse,
    BlogUpdateRequest,
    BlogViewRequest,
)
from app.blog.service import (
    blog_post_to_dict,
    create_blog_post,
    get_blog_post_by_id,
    get_visible_blog_by_slug,
    list_blog_posts,
    publish_blog_post,
    update_blog_post,
)
from app.blog.tracking import get_blog_stats, record_blog_view
from app.common.auth_jwt import AuthJWT, AuthJWTException
from app.common.db import get_db
from app.common.schema import StatusResponse
from app.common.utils import get_user, require_verified

blog_router = APIRouter()


def _require_user(Authorize: AuthJWT, db: Session) -> User:
    """Resolve the current user from the JWT. Raises 401/404."""
    Authorize.jwt_required()
    user = get_user(Authorize.get_jwt_subject(), db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _require_owner_post(post_id: int, user_id: int, db: Session) -> BlogPost:
    """Load a blog post and verify the current user owns it."""
    post = get_blog_post_by_id(post_id, db)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    if post.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return post


@blog_router.post("/create")
def create_blog(
    body: BlogCreateRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> BlogPostResponse:
    user = _require_user(Authorize, db)
    require_verified(user)
    post = create_blog_post(user, body, db)
    return BlogPostResponse.model_validate({"blog_post": blog_post_to_dict(post)})


@blog_router.put("/{post_id}")
def update_blog(
    post_id: int,
    body: BlogUpdateRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> BlogPostResponse:
    user = _require_user(Authorize, db)
    post = _require_owner_post(post_id, user.id, db)
    post = update_blog_post(post, body, db)
    return BlogPostResponse.model_validate({"blog_post": blog_post_to_dict(post)})


@blog_router.post("/{post_id}/publish")
def publish_blog(
    post_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> BlogPostResponse:
    user = _require_user(Authorize, db)
    post = _require_owner_post(post_id, user.id, db)
    post = publish_blog_post(post, db)
    return BlogPostResponse.model_validate({"blog_post": blog_post_to_dict(post)})


@blog_router.get("/list")
def list_blogs(
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    user: str | None = Query(None, max_length=MAX_USERNAME_FILTER_LEN),
    db: Session = Depends(get_db),
) -> BlogListResponse:
    user_id = None
    if user:
        u = get_user(user, db)
        if u:
            user_id = u.id
    posts, has_more = list_blog_posts(db, user_id=user_id, offset=offset, limit=limit)
    return BlogListResponse.model_validate(
        {
            "posts": [blog_post_to_dict(p, include_content=False) for p in posts],
            "has_more": has_more,
        }
    )


@blog_router.get("/my-drafts")
def my_drafts(
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> BlogDraftsResponse:
    user = _require_user(Authorize, db)
    posts, _ = list_blog_posts(db, user_id=user.id, published_only=False)
    drafts = [blog_post_to_dict(p) for p in posts if p.is_draft]
    return BlogDraftsResponse.model_validate({"drafts": drafts})


@blog_router.get("/slug/{slug}")
def get_blog_by_slug(slug: str, db: Session = Depends(get_db)) -> BlogPostResponse:
    post = get_visible_blog_by_slug(slug, db)
    return BlogPostResponse.model_validate({"blog_post": blog_post_to_dict(post)})


@blog_router.post("/{post_id}/view")
def track_view(
    post_id: int,
    request: Request,
    body: BlogViewRequest | None = None,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> StatusResponse:
    body = body or BlogViewRequest.model_validate({})  # fresh per request, never a shared default
    post = get_blog_post_by_id(post_id, db)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")

    user_id = _optional_jwt_user_id(Authorize, db)
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:IP_HASH_LEN]

    record_blog_view(
        blog_post_id=post_id,
        db=db,
        user_id=user_id,
        read_time_seconds=body.read_time_seconds,
        ip_hash=ip_hash,
    )
    return StatusResponse(status="recorded")


def _optional_jwt_user_id(Authorize: AuthJWT, db: Session) -> int | None:
    """Resolve the current user id from the JWT if present, else None.

    Silence is intentional: /blog/{id}/view is public. Only AuthJWTException is
    caught — real errors from the DB layer still propagate.
    """
    try:
        Authorize.jwt_optional()
        username = Authorize.get_jwt_subject()
    except AuthJWTException:
        return None
    if not username:
        return None
    user = get_user(username, db)
    return user.id if user else None


@blog_router.get("/{post_id}/stats")
def blog_stats(
    post_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> BlogStatsResponse:
    user = _require_user(Authorize, db)
    _require_owner_post(post_id, user.id, db)
    return BlogStatsResponse.model_validate(get_blog_stats(post_id, db))
