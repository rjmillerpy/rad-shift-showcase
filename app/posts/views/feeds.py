"""Feed endpoints: `/`, `/algo`, `/trending`, `/random`, `/branches`, `/media`, `/following`,
`/tags`, and following topics (`/topics/follow`, `/topics/unfollow`)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import optional_user, required_user

from ..branches import follow, get_branch_posts_formatted, unfollow
from ..feeds import (
    get_algo_posts_formatted,
    get_all_posts_formatted,
    get_followed_posts_formatted,
    get_media_posts_formatted,
    get_trending_posts_formatted,
)
from ..random_feed import MAX_RANDOM_OFFSET, get_random_posts_formatted
from ..schema import (
    BranchPageResponse,
    BranchResponse,
    FollowedTopicsResponse,
    PostPageResponse,
    TagsResponse,
    TopicRequest,
)
from ..search import get_feed_tags

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
# The frontend picks a seed per shuffle; any 31-bit number.
MAX_SEED = 2**31 - 1


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


@router.get("/trending")
def get_trending_posts(
    offset: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> PostPageResponse:
    """Most engagement in the last hours (scores fed by Kafka; empty without it)."""
    posts, has_more = get_trending_posts_formatted(
        db=db,
        current_user=current_user,
        offset=offset,
        limit=limit,
    )
    return PostPageResponse(posts=posts, has_more=has_more)


@router.get("/random")
def get_random_posts(
    seed: int = Query(0, ge=0, le=MAX_SEED),
    offset: int = Query(0, ge=0, le=MAX_RANDOM_OFFSET),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> PostPageResponse:
    """People's and scraped posts taking turns, shuffled by `seed` (app/posts/random_feed.py)."""
    posts, has_more = get_random_posts_formatted(
        db=db, seed=seed, current_user=current_user, offset=offset, limit=limit
    )
    return PostPageResponse(posts=posts, has_more=has_more)


@router.get("/branches")
def get_branch_posts(
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    current_user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> BranchPageResponse:
    """Topics next to the ones you follow, and posts on them (app/posts/branches.py)."""
    branches, posts, has_more = get_branch_posts_formatted(db, current_user, offset, limit)
    return BranchPageResponse(
        branches=[BranchResponse(topic=b.topic, via=b.via, posts=b.posts) for b in branches],
        posts=posts,
        has_more=has_more,
    )


@router.post("/topics/follow")
def follow_topic(
    body: TopicRequest,
    current_user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> FollowedTopicsResponse:
    """Follow a topic: it joins your Bubbles topics and roots new branches."""
    return FollowedTopicsResponse(topics=follow(current_user, body.topic, db))


@router.post("/topics/unfollow")
def unfollow_topic(
    body: TopicRequest,
    current_user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> FollowedTopicsResponse:
    return FollowedTopicsResponse(topics=unfollow(current_user, body.topic, db))


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
