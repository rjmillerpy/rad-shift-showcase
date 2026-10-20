"""Blog post CRUD and visibility rules."""

import logging
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.blog.constants import (
    LIST_PREVIEW_LEN,
    MAX_SEO_TITLE_LEN,
    AdPlacement,
)
from app.blog.content import (
    auto_seo_description,
    estimate_reading_time,
    generate_slug,
    sanitize_html,
    strip_html,
)
from app.blog.models import BlogPost
from app.blog.schema import BlogCreateRequest, BlogUpdateRequest

logger = logging.getLogger(__name__)


_UPDATE_ALLOWED_FIELDS = {
    "title",
    "content_html",
    "featured_image_url",
    "seo_title",
    "seo_description",
    "tags",
    "category",
    "monetized",
    "ad_placement",
    "is_draft",
    "og_title",
    "og_description",
    "og_image",
}


def _unique_slug(base_slug: str, db: Session) -> str:
    """Return `base_slug`, or `base_slug-N` for the smallest N that is free."""
    existing = {
        row[0] for row in db.query(BlogPost.slug).filter(BlogPost.slug.like(f"{base_slug}%")).all()
    }
    if base_slug not in existing:
        return base_slug
    counter = 2
    while f"{base_slug}-{counter}" in existing:
        counter += 1
    return f"{base_slug}-{counter}"


def create_blog_post(user: User, body: BlogCreateRequest, db: Session) -> BlogPost:
    """Create a new blog post from a validated request body."""
    title = body.title.strip()
    content_html = sanitize_html(body.content_html)
    plain_text = strip_html(content_html)
    slug = _unique_slug(generate_slug(title), db)

    now = int(time.time())
    is_published = not body.is_draft
    ad_placement = body.ad_placement.value if body.monetized else AdPlacement.NONE.value

    post = BlogPost(
        user_id=user.id,
        slug=slug,
        title=title,
        content_html=content_html,
        content_text=plain_text,
        featured_image_url=body.featured_image_url,
        seo_title=body.seo_title or title[:MAX_SEO_TITLE_LEN],
        seo_description=body.seo_description or auto_seo_description(content_html),
        tags=body.tags,
        category=body.category,
        monetized=body.monetized,
        ad_placement=ad_placement,
        og_title=body.og_title or title[:MAX_SEO_TITLE_LEN],
        og_description=body.og_description or auto_seo_description(content_html),
        og_image=body.og_image or body.featured_image_url,
        is_draft=body.is_draft,
        is_published=is_published,
        published_at=now if is_published else None,
        created_at=now,
        reading_time_minutes=estimate_reading_time(plain_text),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    logger.info("Blog post created id=%s slug=%s user=%s", post.id, post.slug, user.id)
    return post


def _serialise_ad_placement(value: AdPlacement | str) -> str:
    return value.value if isinstance(value, AdPlacement) else value


def update_blog_post(post: BlogPost, body: BlogUpdateRequest, db: Session) -> BlogPost:
    """Apply a partial update to a blog post."""
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key not in _UPDATE_ALLOWED_FIELDS or value is None:
            continue
        if key == "ad_placement":
            value = _serialise_ad_placement(value)
        if key == "content_html":
            value = sanitize_html(value)
        setattr(post, key, value)

    if "content_html" in updates:
        post.content_text = strip_html(post.content_html)
        post.reading_time_minutes = estimate_reading_time(post.content_text)
        if "seo_description" not in updates:
            post.seo_description = auto_seo_description(post.content_html)

    if not post.monetized:
        post.ad_placement = AdPlacement.NONE.value

    post.updated_at = int(time.time())
    db.commit()
    db.refresh(post)
    logger.info("Blog post updated id=%s", post.id)
    return post


def publish_blog_post(post: BlogPost, db: Session) -> BlogPost:
    """Publish a draft blog post."""
    now = int(time.time())
    post.is_draft = False
    post.is_published = True
    post.published_at = now
    post.updated_at = now
    db.commit()
    db.refresh(post)
    logger.info("Blog post published id=%s", post.id)
    return post


def get_blog_post_by_slug(slug: str, db: Session) -> BlogPost | None:
    return db.query(BlogPost).filter_by(slug=slug).first()


def get_blog_post_by_id(post_id: int, db: Session) -> BlogPost | None:
    return db.query(BlogPost).filter_by(id=post_id).first()


def get_visible_blog_by_slug(slug: str, db: Session) -> BlogPost:
    """Fetch a blog by slug and enforce public visibility. Raises 404 if hidden."""
    post = get_blog_post_by_slug(slug, db)
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    if not post.is_published and not post.is_draft:
        # Neither published nor an accessible draft — treat as absent.
        raise HTTPException(status_code=404, detail="Blog post not found")
    return post


def list_blog_posts(
    db: Session,
    *,
    user_id: int | None = None,
    published_only: bool = True,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[BlogPost], bool]:
    """List blog posts with pagination."""
    query = db.query(BlogPost)
    if user_id:
        query = query.filter(BlogPost.user_id == user_id)
    if published_only:
        query = query.filter(BlogPost.is_published.is_(True))
    query = query.order_by(BlogPost.created_at.desc())
    rows = query.offset(offset).limit(limit + 1).all()
    has_more = len(rows) > limit
    return rows[:limit], has_more


def blog_post_to_dict(post: BlogPost, include_content: bool = True) -> dict:
    """Serialise a blog post to a dict. Includes full content unless `include_content=False`."""
    d: dict[str, Any] = {
        "id": post.id,
        "slug": post.slug,
        "title": post.title,
        "featured_image_url": post.featured_image_url,
        "seo_title": post.seo_title,
        "seo_description": post.seo_description,
        "tags": post.tags or [],
        "category": post.category,
        "og_title": post.og_title,
        "og_description": post.og_description,
        "og_image": post.og_image,
        "monetized": post.monetized,
        "ad_placement": post.ad_placement,
        "is_draft": post.is_draft,
        "is_published": post.is_published,
        "published_at": post.published_at,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "reading_time_minutes": post.reading_time_minutes,
        "view_count": post.view_count,
        "username": post.user.username if post.user else None,
        "profile_picture_url": post.user.profile_picture_url if post.user else None,
    }
    if include_content:
        d["content_html"] = post.content_html
        d["content_text"] = post.content_text
    else:
        d["preview"] = (post.content_text or "")[:LIST_PREVIEW_LEN]
    return d
