"""Pydantic schemas for the generator/scraper system."""

from typing import Any

from pydantic import BaseModel, Field

from app.common.schema import FrozenModel

# The shape of a platform name. Which platforms exist is the edition's
# business (app/generators/platforms/base.py); the service rejects the rest.
PLATFORM_NAME_REGEX = r"^[a-z][a-z0-9_]{0,31}$"
# Topics tagged on every post from a source (SourceConfig.topics).
MAX_SOURCE_TOPICS = 10


class SelectorConfig(BaseModel):
    """CSS selectors for extracting content from a page."""

    post_container: str = Field(..., description="CSS selector for each post/article element")
    title: str | None = Field(None, description="Selector for post title within container")
    text: str = Field(..., description="Selector for post text/body within container")
    image: str | None = Field(None, description="Selector for image within container")
    link: str | None = Field(None, description="Selector for permalink within container")
    popularity: str | None = Field(None, description="Selector for like/vote/score element")


class SourceConfig(BaseModel):
    """Scraping preferences for a source."""

    content_types: list[str] = Field(
        default=["text"], description="Types to scrape: text, image, link"
    )
    max_items_per_run: int = Field(default=10, ge=1, le=100)
    min_popularity: int = Field(default=0, ge=0, description="Minimum score/likes to include")
    dedupe_field: str = Field(
        default="text", description="Field to deduplicate on: text, link, title"
    )
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    # Tagged on every post from this source, for tailored feeds (app/posts/topics.py).
    topics: list[str] = Field(default_factory=list, max_length=MAX_SOURCE_TOPICS)
    use_browser: bool = Field(
        default=False, description="Use headless browser for JS-rendered sites"
    )
    browser_engine: str = Field(
        default="chromium",
        pattern="^(chromium|firefox)$",
        description="Browser engine when use_browser=True — 'firefox' for TLS-sensitive sites like nitter.net",
    )


class SourceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    site_url: str = Field(..., min_length=1, max_length=2000)
    description: str | None = None
    config: SourceConfig | None = None
    run_interval_minutes: int = Field(default=0, ge=0, le=1440)
    platform: str = Field(default="web", pattern=PLATFORM_NAME_REGEX)
    platform_config: dict[str, Any] | None = None


class SourceUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=200)
    site_url: str | None = Field(None, max_length=2000)
    description: str | None = None
    config: SourceConfig | None = None
    is_active: bool | None = None
    run_interval_minutes: int | None = Field(None, ge=0, le=1440)
    platform: str | None = Field(None, pattern=PLATFORM_NAME_REGEX)
    platform_config: dict[str, Any] | None = None


class ProfileCreateRequest(BaseModel):
    source_id: int
    user_id: int


class RunSourceRequest(BaseModel):
    """Trigger a manual scrape run."""

    source_id: int


class AnalyzeRequest(BaseModel):
    """Ask AI to analyze a URL and generate selectors."""

    site_url: str = Field(..., min_length=1, max_length=2000)
    content_hint: str | None = Field(
        None,
        max_length=500,
        description="Hint about what content to look for, e.g. 'trending memes', 'tech news headlines'",
    )
    browser_engine: str = Field(
        default="chromium",
        pattern="^(chromium|firefox)$",
        description="Browser engine to use — 'firefox' for TLS-sensitive sites",
    )


# ── Responses ──────────────────────────────────────────────────────────────
# selectors, config and platform_config are free-form JSON columns whose keys
# depend on the platform, so they stay open dicts.


class GeneratorSourceOut(FrozenModel):
    id: int
    name: str
    site_url: str
    description: str | None
    platform: str
    platform_config: dict[str, Any] | None
    selectors: dict[str, Any] | None
    config: dict[str, Any] | None
    is_active: bool
    last_run_at: int | None
    last_error: str | None
    total_posts_created: int
    consecutive_failures: int
    run_interval_minutes: int
    profile_count: int


class GeneratorSourceResponse(FrozenModel):
    source: GeneratorSourceOut


class GeneratorSourcesResponse(FrozenModel):
    sources: list[GeneratorSourceOut]


class GeneratorProfileOut(FrozenModel):
    id: int
    source_id: int
    user_id: int
    username: str | None
    is_active: bool


class GeneratorProfileResponse(FrozenModel):
    profile: GeneratorProfileOut


class GeneratorProfilesResponse(FrozenModel):
    profiles: list[GeneratorProfileOut]


class GeneratorRunOut(FrozenModel):
    id: int
    source_id: int
    started_at: int
    finished_at: int | None
    status: str
    items_found: int
    items_posted: int
    error_message: str | None
    selectors_updated: bool


class GeneratorRunResponse(FrozenModel):
    run: GeneratorRunOut


class GeneratorRunsResponse(FrozenModel):
    runs: list[GeneratorRunOut]


class SelectorsResponse(FrozenModel):
    selectors: dict[str, Any]


class SelectorsSavedResponse(FrozenModel):
    selectors: dict[str, Any]
    status: str


class TemplateFieldOut(FrozenModel):
    key: str
    label: str
    placeholder: str
    pattern: str
    help: str
    required: bool
    takes_topic: bool


class SourceTemplateOut(FrozenModel):
    id: str
    name: str
    description: str
    platform: str
    fields: list[TemplateFieldOut]


class SourceTemplatesResponse(FrozenModel):
    templates: list[SourceTemplateOut]


class TemplateSourceRequest(BaseModel):
    """A template's field values, by field key (app/generators/templates.py)."""

    values: dict[str, str] = Field(default_factory=dict, max_length=10)


class TemplateSourceResponse(FrozenModel):
    source: GeneratorSourceOut
    bot_username: str  # the account it posts as, made with it


class WantedTopicOut(FrozenModel):
    topic: str
    readers: int
    posts: int
    thin: bool


class WantedTopicsResponse(FrozenModel):
    topics: list[WantedTopicOut]
