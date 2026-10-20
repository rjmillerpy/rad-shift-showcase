"""Request schemas, the PostResponse DTO, and the response envelopes every
posts endpoint returns (rule 46: one schema per response shape, defined here
as the single source of truth).
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.common.schema import FrozenModel

from .constants import MAX_POST_TEXT_CHARS


class PostCreateRequest(BaseModel):
    text: str = Field(..., max_length=MAX_POST_TEXT_CHARS)
    post_metadata: str = "{}"
    is_draft: bool = False
    parent_post_id: int | None = None
    is_reply: bool = False


class SlopRequest(BaseModel):
    reason: str = Field(..., min_length=1)


@dataclass
class PostResponse:
    """Internal DTO used by the feed/serializer layers.

    Not a Pydantic model on purpose — it's serialised with `dataclasses.asdict`
    on the view boundary and the dataclass gives cheaper construction (rule 63
    — avoid unnecessary Pydantic validation on the hot path).
    """

    id: int
    text: str
    likes: int
    shares: int
    reposts: int
    saves: int
    laughs: int
    liked_by_me: bool
    # Nullable in the database (legacy rows), so it must not fail validation.
    unix_timestamp: int | None
    post_metadata: dict
    username: str
    profile_picture_url: str | None
    image_url: str | None
    video_url: str | None
    audio_url: str | None
    image_urls: list[str] | None = None
    document_urls: list[str] | None = None
    replies_count: int = 0
    quotes_count: int = 0
    slop_count: int = 0
    reposted_by: list[str] | None = None
    reposted_by_me: bool | None = None
    is_followed_by_me: bool | None = None
    is_saved_by_me: bool | None = None
    laughed_by_me: bool | None = None
    is_me: bool | None = None
    media_metadata: dict | None = None
    quoted_post: dict | None = None


# ── Response envelopes ─────────────────────────────────────────────────────


class PostPageResponse(FrozenModel):
    """One page of a feed or search."""

    posts: list[PostResponse]
    has_more: bool


class SavedPostsResponse(FrozenModel):
    posts: list[PostResponse]


class DraftsResponse(FrozenModel):
    drafts: list[PostResponse]


class SinglePostResponse(FrozenModel):
    post: PostResponse


class RepliesResponse(FrozenModel):
    replies: list[PostResponse]


class PostCreatedResponse(FrozenModel):
    message: str
    image_url: str | None
    image_urls: list[str] | None
    video_url: str | None
    audio_url: str | None
    document_urls: list[str] | None


class PostStatusResponse(FrozenModel):
    """Outcome of an action on one post (publish a draft, report slop)."""

    status: str
    post_id: int


class LikeToggleResponse(FrozenModel):
    likes: int
    action: str


class LaughToggleResponse(FrozenModel):
    laughs: int
    action: str


class RepostToggleResponse(FrozenModel):
    reposts: int
    action: str


class SaveToggleResponse(FrozenModel):
    saves: int
    action: str


class ShareResponse(FrozenModel):
    share_url: str
    shares: int


class TagsResponse(FrozenModel):
    tags: list[str]


class UserSummary(FrozenModel):
    username: str
    bio: str | None
    profile_picture_url: str | None


class UserSearchResponse(FrozenModel):
    users: list[UserSummary]
    has_more: bool


class ChronicleSegment(FrozenModel):
    """A narrative chunk. `text` and `index` are present only on the segment
    types that use them, so the endpoint serialises with exclude_unset."""

    type: str
    text: str | None = None
    index: int | None = None


class ChronicleResponse(FrozenModel):
    posts: list[PostResponse]
    segments: list[ChronicleSegment]
    page: int
    has_more: bool
    cached: bool
