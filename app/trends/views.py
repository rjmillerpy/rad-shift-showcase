"""Public REST endpoints for the trends aggregator."""

import logging

from fastapi import APIRouter, Query

from app.trends import service
from app.trends.schema import ALL_SOURCES, TrendsResponse

logger = logging.getLogger(__name__)

# Cap the raw `sources` query string. Longest legitimate value is every source
# joined by commas (~40 chars today); 200 leaves generous headroom for future
# sources without letting the query balloon (rule 5/11).
MAX_SOURCES_QUERY_CHARS = 200

trends_router = APIRouter()


@trends_router.get("/", response_model=TrendsResponse)
def list_trends(
    sources: str | None = Query(
        None,
        max_length=MAX_SOURCES_QUERY_CHARS,
        description=(
            "Comma-separated source names to include. "
            f"Allowed: {', '.join(ALL_SOURCES)}. Defaults to all."
        ),
    ),
) -> TrendsResponse:
    """Return the latest trends for each requested source (cached 15 min)."""
    requested = _parse_source_list(sources)
    bundles = service.get_trends(requested)
    return TrendsResponse(sources=bundles)


@trends_router.post("/refresh", response_model=TrendsResponse)
def refresh_trends() -> TrendsResponse:
    """Drop cached bundles and re-fetch all sources immediately."""
    service.clear_cache()
    bundles = service.get_trends(None)
    return TrendsResponse(sources=bundles)


def _parse_source_list(raw: str | None) -> list[str] | None:
    """Split a comma-separated source list into a clean list (or None for 'all')."""
    if not raw:
        return None
    parts = [s.strip() for s in raw.split(",") if s.strip()]
    return parts or None
