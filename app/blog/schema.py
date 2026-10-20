"""Pydantic request and response schemas for blog endpoints."""

from typing import Annotated

from pydantic import BaseModel, Field

from app.blog.constants import (
    MAX_CATEGORY_LEN,
    MAX_READ_TIME_SECONDS,
    MAX_SEO_DESCRIPTION_LEN,
    MAX_SEO_TITLE_LEN,
    MAX_TITLE_LEN,
    AdPlacement,
)
from app.common.schema import FrozenModel

# Each field's constraints, stated once: create requires some of them,
# update makes everything optional, and both validate the same way.
Title = Annotated[str, Field(min_length=1, max_length=MAX_TITLE_LEN)]
Body = Annotated[str, Field(min_length=1)]
SeoTitle = Annotated[str, Field(max_length=MAX_SEO_TITLE_LEN)]
SeoDescription = Annotated[str, Field(max_length=MAX_SEO_DESCRIPTION_LEN)]
Category = Annotated[str, Field(max_length=MAX_CATEGORY_LEN)]


class BlogCreateRequest(BaseModel):
    title: Title
    content_html: Body
    featured_image_url: str | None = None
    seo_title: SeoTitle | None = None
    seo_description: SeoDescription | None = None
    tags: list[str] | None = None
    category: Category | None = None
    monetized: bool = False
    ad_placement: AdPlacement = AdPlacement.NONE
    og_title: SeoTitle | None = None
    og_description: SeoDescription | None = None
    og_image: str | None = None
    is_draft: bool = True


class BlogUpdateRequest(BaseModel):
    title: Title | None = None
    content_html: Body | None = None
    featured_image_url: str | None = None
    seo_title: SeoTitle | None = None
    seo_description: SeoDescription | None = None
    tags: list[str] | None = None
    category: Category | None = None
    monetized: bool | None = None
    ad_placement: AdPlacement | None = None
    og_title: SeoTitle | None = None
    og_description: SeoDescription | None = None
    og_image: str | None = None
    is_draft: bool | None = None


class BlogViewRequest(BaseModel):
    read_time_seconds: int = Field(0, ge=0, le=MAX_READ_TIME_SECONDS)


# ── Responses ──────────────────────────────────────────────────────────────


class BlogPostSummary(FrozenModel):
    """Fields every blog-post response carries. The two concrete shapes below
    add either the full content or a short preview."""

    id: int
    slug: str
    title: str
    featured_image_url: str | None
    seo_title: str | None
    seo_description: str | None
    tags: list[str]
    category: str | None
    og_title: str | None
    og_description: str | None
    og_image: str | None
    monetized: bool
    ad_placement: str
    is_draft: bool
    is_published: bool
    published_at: int | None
    created_at: int
    updated_at: int | None
    reading_time_minutes: int
    view_count: int
    username: str | None
    profile_picture_url: str | None


class BlogPostDetail(BlogPostSummary):
    content_html: str
    content_text: str | None


class BlogPostPreview(BlogPostSummary):
    preview: str


class BlogPostResponse(FrozenModel):
    blog_post: BlogPostDetail


class BlogListResponse(FrozenModel):
    posts: list[BlogPostPreview]
    has_more: bool


class BlogDraftsResponse(FrozenModel):
    drafts: list[BlogPostDetail]


class BlogStatsResponse(FrozenModel):
    view_count: int
    total_read_time_seconds: int
    unique_readers: int
    reading_time_minutes: int
