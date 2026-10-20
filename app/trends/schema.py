"""Pydantic schemas and source constants for the trends aggregator."""

from pydantic import Field

from app.common.schema import FrozenModel

SOURCE_TRENDS24 = "trends24"
SOURCE_GOOGLE = "google"
SOURCE_REDDIT = "reddit"
SOURCE_HN = "hackernews"

SOURCE_LABELS = {
    SOURCE_TRENDS24: "X (via trends24)",
    SOURCE_GOOGLE: "Google Search",
    SOURCE_REDDIT: "Reddit Popular",
    SOURCE_HN: "Hacker News",
}

ALL_SOURCES = tuple(SOURCE_LABELS.keys())


class TrendItem(FrozenModel):
    """A single trending keyword/topic/story from some source."""

    source: str = Field(..., description="Source identifier, e.g. 'trends24'")
    rank: int = Field(..., ge=1, description="1-indexed rank within the source's list")
    keyword: str = Field(..., min_length=1, max_length=500)
    url: str | None = Field(None, max_length=2000, description="Deep link to the item/search")
    volume: str | None = Field(
        None, max_length=100, description="Display volume — '200K+', '4,521 upvotes'"
    )
    category: str | None = Field(None, max_length=100, description="Section or subreddit")


class SourceTrends(FrozenModel):
    """A bundle of trend items from one source, with metadata."""

    source: str
    label: str
    items: list[TrendItem]
    fetched_at: int = Field(..., description="Unix timestamp when this bundle was last fetched")
    error: str | None = Field(
        None, description="Error message if the fetch failed; items will be empty"
    )


class TrendsResponse(FrozenModel):
    """Aggregated trends across all requested sources."""

    sources: list[SourceTrends]
