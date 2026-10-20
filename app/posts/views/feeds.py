"""Feed endpoints: `/`, `/algo`, `/media`, `/following`, `/tags`."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import optional_user, required_user

from ..feeds import (
    get_algo_posts_formatted,
    get_all_posts_formatted,
    get_followed_posts_formatted,
    get_media_posts_formatted,
)
from ..schema import PostPageResponse, TagsResponse
from ..search import get_feed_tags

DEFAULT_PAGE_LIMIT = 20


router = APIRouter()


@router.get("/")
def get_posts(
    offset: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> PostPageResponse:
    posts, has_more = get_all_posts_formatted(
        db=db,
        current_user=current_user,
        offset=offset,
        limit=limit,
    )
    return PostPageResponse(posts=posts, has_more=has_more)


@router.get("/algo")
def get_algo_posts(
    offset: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> PostPageResponse:
    posts, has_more = get_algo_posts_formatted(
        db=db,
        current_user=current_user,
        offset=offset,
        limit=limit,
    )
    return PostPageResponse(posts=posts, has_more=has_more)


@router.get("/media")
def get_media_posts(
    media_type: str = "all",
    offset: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> PostPageResponse:
    """Return posts that have audio or video attachments."""
    posts, has_more = get_media_posts_formatted(
        db=db,
        current_user=current_user,
        media_type=media_type,
        offset=offset,
        limit=limit,
    )
    return PostPageResponse(posts=posts, has_more=has_more)


@router.get("/following")
def get_following_posts(
    offset: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> PostPageResponse:
    posts, has_more = get_followed_posts_formatted(
        user,
        db,
        offset=offset,
        limit=limit,
    )
    return PostPageResponse(posts=posts, has_more=has_more)


@router.get("/tags")
def get_tags(
    feed: str = "main",
    limit: int = 10,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> TagsResponse:
    tags = get_feed_tags(db, feed=feed, current_user=current_user, limit=limit)
    return TagsResponse(tags=tags)
