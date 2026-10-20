"""What every generator platform produces, and the filters the service applies to it."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScrapedItem:
    """A single piece of content extracted from a page."""

    title: str | None
    text: str
    image_url: str | None
    link: str | None
    popularity: int
    # When True, ``image_url`` is a still thumbnail and the actual content at
    # ``link`` is a video. Frontend uses this to overlay a play-button affordance.
    is_video: bool = False


def filter_items(
    items: list[ScrapedItem],
    *,
    min_popularity: int = 0,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    max_items: int = 10,
) -> list[ScrapedItem]:
    """Filter and rank scraped items by popularity and keywords."""
    filtered = [i for i in items if i.popularity >= min_popularity]

    if include_keywords:
        lower_keywords = {k.lower() for k in include_keywords}
        filtered = [
            i
            for i in filtered
            if any(kw in (i.text + " " + (i.title or "")).lower() for kw in lower_keywords)
        ]

    if exclude_keywords:
        lower_excludes = {k.lower() for k in exclude_keywords}
        filtered = [
            i
            for i in filtered
            if not any(kw in (i.text + " " + (i.title or "")).lower() for kw in lower_excludes)
        ]

    # Sort by popularity descending, take top N
    filtered.sort(key=lambda i: i.popularity, reverse=True)
    return filtered[:max_items]
