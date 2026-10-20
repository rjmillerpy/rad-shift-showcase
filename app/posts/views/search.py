"""Search endpoints: `/search/posts`, `/search/users`."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import optional_user

from ..schema import PostPageResponse, UserSearchResponse
from ..search import search_posts_formatted, search_users
from .feeds import DEFAULT_PAGE_LIMIT

router = APIRouter()


@router.get("/search/posts")
def search_posts_endpoint(
    q: str = "",
    offset: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> PostPageResponse:
    query = q.strip()
    if not query:
        return PostPageResponse(posts=[], has_more=False)
    posts, has_more = search_posts_formatted(
        query,
        db,
        current_user=current_user,
        offset=offset,
        limit=limit,
    )
    return PostPageResponse(posts=posts, has_more=has_more)


@router.get("/search/users")
def search_users_endpoint(
    q: str = "",
    offset: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
    db: Session = Depends(get_db),
) -> UserSearchResponse:
    query = q.strip()
    if not query:
        return UserSearchResponse(users=[], has_more=False)
    users, has_more = search_users(query, db, offset=offset, limit=limit)
    return UserSearchResponse.model_validate({"users": users, "has_more": has_more})
