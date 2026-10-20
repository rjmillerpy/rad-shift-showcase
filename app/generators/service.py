"""Business logic for managing generator sources, profiles, and scrape runs."""

import logging
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User

from .constants import (
    DEFAULT_BROWSER_ENGINE,
    DEFAULT_RUN_LIMIT,
    FETCH_FAILURE_STATUS,
    GENERIC_FAILURE_STATUS,
    MAX_CONSECUTIVE_FAILURES,
    MAX_ERROR_MESSAGE_CHARS,
    RunStatus,
)
from .items import ScrapedItem, filter_items
from .models import GeneratorProfile, GeneratorRun, GeneratorSource
from .platforms.base import PLATFORM_WEB, PlatformConfigError, get_adapter, is_platform_supported
from .posting import post_filtered_items
from .schema import SourceUpdateRequest
from .web import web_scraper

logger = logging.getLogger(__name__)


# ── Source CRUD ──────────────────────────────────────────────────────


def list_sources(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
) -> list[GeneratorSource]:
    return (
        db.query(GeneratorSource)
        .order_by(GeneratorSource.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_source(source_id: int, db: Session) -> GeneratorSource:
    source = db.query(GeneratorSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


def create_source(
    name: str,
    site_url: str,
    db: Session,
    *,
    description: str | None = None,
    config: dict | None = None,
    run_interval_minutes: int = 0,
    platform: str = PLATFORM_WEB,
    platform_config: dict | None = None,
) -> GeneratorSource:
    _validate_platform_at_create(platform, platform_config)
    source = GeneratorSource(
        name=name,
        site_url=site_url,
        description=description,
        config=config or {},
        run_interval_minutes=run_interval_minutes,
        platform=platform,
        platform_config=platform_config or {},
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _validate_platform_at_create(platform: str, platform_config: dict | None) -> None:
    """Ensure the platform is known and its config validates before persisting."""
    if platform == PLATFORM_WEB:
        web_scraper()
        return
    try:
        adapter = get_adapter(platform)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        adapter.validate_config(platform_config or {})
    except PlatformConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


_UPDATE_ALLOWED_FIELDS = {
    "name",
    "site_url",
    "description",
    "config",
    "is_active",
    "run_interval_minutes",
    "platform",
    "platform_config",
}


def update_source(
    source_id: int,
    body: SourceUpdateRequest,
    db: Session,
) -> GeneratorSource:
    source = get_source(source_id, db)
    if body.platform is not None and not is_platform_supported(body.platform):
        raise HTTPException(status_code=422, detail=f"Unsupported platform '{body.platform}'")
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key not in _UPDATE_ALLOWED_FIELDS:
            continue
        if key == "config" and hasattr(value, "dict"):
            value = value.model_dump()
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


def delete_source(source_id: int, db: Session) -> None:
    source = get_source(source_id, db)
    db.delete(source)
    db.commit()


# ── Profile CRUD ─────────────────────────────────────────────────────


def list_profiles(source_id: int, db: Session) -> list[GeneratorProfile]:
    return db.query(GeneratorProfile).filter_by(source_id=source_id).all()


def attach_profile(source_id: int, user_id: int, db: Session) -> GeneratorProfile:
    existing = db.query(GeneratorProfile).filter_by(source_id=source_id, user_id=user_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Profile already attached")

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = GeneratorProfile(source_id=source_id, user_id=user_id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def detach_profile(profile_id: int, db: Session) -> None:
    profile = db.query(GeneratorProfile).filter_by(id=profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(profile)
    db.commit()


# ── Run history ──────────────────────────────────────────────────────


def list_runs(
    source_id: int,
    db: Session,
    limit: int = DEFAULT_RUN_LIMIT,
) -> list[GeneratorRun]:
    return (
        db.query(GeneratorRun)
        .filter_by(source_id=source_id)
        .order_by(GeneratorRun.id.desc())
        .limit(limit)
        .all()
    )


# ── Scraper orchestration ───────────────────────────────────────────


def _validate_selectors(selectors: dict | None) -> None:
    """Ensure selectors dict has usable values.

    Requires post_container plus at least one content selector (text OR title).
    Title-only is legitimate for link-aggregator sites like Hacker News whose
    listing pages have no body element — the extractor falls back to title as
    the post body in that case.
    """
    if not selectors:
        raise HTTPException(status_code=422, detail="No selectors configured — run Analyze first")

    container = selectors.get("post_container")
    if not container:
        raise HTTPException(
            status_code=422,
            detail=(
                "Selectors are incomplete — post_container is required. "
                "This usually means the site renders content with JavaScript. "
                "Try a site that serves HTML content directly (blogs, forums, RSS feeds)."
            ),
        )

    if not selectors.get("text") and not selectors.get("title"):
        raise HTTPException(
            status_code=422,
            detail=(
                "Selectors are incomplete — at least one of text or title must be set. "
                "The analyzer found no content elements; this usually means the site "
                "renders content with JavaScript."
            ),
        )


def run_scraper(source_id: int, db: Session) -> GeneratorRun:
    """Execute a full scrape cycle for a source."""
    source = get_source(source_id, db)
    _validate_source_for_run(source)

    run = GeneratorRun(
        source_id=source_id,
        started_at=int(time.time()),
        status=RunStatus.RUNNING.value,
    )
    db.add(run)
    db.commit()

    try:
        if source.platform == PLATFORM_WEB:
            return _execute_scrape(source, run, db)
        return _execute_platform_scrape(source, run, db)
    except HTTPException:
        raise
    except ConnectionError as exc:
        _record_run_failure(run, source, exc, db)
        raise HTTPException(
            status_code=FETCH_FAILURE_STATUS,
            detail=f"Could not fetch site: {_truncate_error(exc)}",
        ) from exc
    except (ValueError, RuntimeError) as exc:
        _record_run_failure(run, source, exc, db)
        raise HTTPException(
            status_code=GENERIC_FAILURE_STATUS,
            detail=f"Scraper run failed: {_truncate_error(exc)}",
        ) from exc


def _validate_source_for_run(source: GeneratorSource) -> None:
    """Pre-run validation — platform-aware."""
    if source.platform == PLATFORM_WEB:
        web_scraper()
        _validate_selectors(source.selectors)
        return
    try:
        adapter = get_adapter(source.platform)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        adapter.validate_config(source.platform_config or {})
    except PlatformConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _execute_platform_scrape(
    source: GeneratorSource,
    run: GeneratorRun,
    db: Session,
) -> GeneratorRun:
    """Fetch via the registered adapter, then share the common filter/post pipeline."""
    config: dict[str, Any] = source.config or {}
    adapter = get_adapter(source.platform)
    max_items = int(config.get("max_items_per_run", 10))
    items = adapter.fetch_items(source.platform_config or {}, max_items)
    filtered = _filter_scraped_items(items, config)

    run.items_found = len(items)
    posted = post_filtered_items(source, filtered, db)
    _finalize_successful_run(run, source, posted, db)
    return run


def _truncate_error(exc: Exception) -> str:
    """Cap error messages so we never leak unbounded internal details to clients."""
    return str(exc)[:MAX_ERROR_MESSAGE_CHARS]


def _record_run_failure(
    run: GeneratorRun,
    source: GeneratorSource,
    exc: Exception,
    db: Session,
) -> None:
    """Persist a failed run and bump the source's failure counter."""
    error_msg = _truncate_error(exc)
    run.status = RunStatus.FAILED.value
    run.error_message = error_msg
    run.finished_at = int(time.time())
    source.consecutive_failures += 1
    source.last_error = error_msg
    db.commit()
    logger.error("Scrape failed for source %d: %s", source.id, exc)


def _execute_scrape(source: GeneratorSource, run: GeneratorRun, db: Session) -> GeneratorRun:
    """Core scrape logic — fetch, extract, heal selectors if needed, post."""
    config: dict[str, Any] = source.config or {}
    html = _fetch_source_html(source, config)
    items, selectors_healed = _extract_with_healing(source, html, config)
    filtered = _filter_scraped_items(items, config)

    run.items_found = len(items)
    run.selectors_updated = selectors_healed

    posted = post_filtered_items(source, filtered, db)

    _finalize_successful_run(run, source, posted, db)
    return run


def _fetch_source_html(source: GeneratorSource, config: dict) -> str:
    """Fetch the source URL using the configured browser strategy."""
    return web_scraper().fetch_page(
        source.site_url,
        use_browser=config.get("use_browser", False),
        browser_engine=config.get("browser_engine", DEFAULT_BROWSER_ENGINE),
    )


def _extract_with_healing(
    source: GeneratorSource,
    html: str,
    config: dict,
) -> tuple[list[ScrapedItem], bool]:
    """Extract items, re-analyzing selectors once if none were found."""
    scraper = web_scraper()
    items = scraper.extract_items(html, source.selectors)
    if items or source.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return items, False

    logger.info("No items found for source %d, attempting selector healing", source.id)
    new_selectors = scraper.heal_selectors(
        source.site_url,
        source.selectors,
        config.get("content_hint", source.description or ""),
        use_browser=config.get("use_browser", False),
        browser_engine=config.get("browser_engine", DEFAULT_BROWSER_ENGINE),
    )
    if not new_selectors:
        return items, False

    new_items = scraper.extract_items(html, new_selectors)
    if not new_items:
        return items, False

    source.selectors = new_selectors
    logger.info("Selectors healed for source %d", source.id)
    return new_items, True


def _filter_scraped_items(items: list[ScrapedItem], config: dict) -> list[ScrapedItem]:
    """Apply the source's keyword/popularity/limit filters."""
    return filter_items(
        items,
        min_popularity=config.get("min_popularity", 0),
        include_keywords=config.get("include_keywords"),
        exclude_keywords=config.get("exclude_keywords"),
        max_items=config.get("max_items_per_run", 10),
    )


def _finalize_successful_run(
    run: GeneratorRun,
    source: GeneratorSource,
    posted: int,
    db: Session,
) -> None:
    """Mark the run as successful and reset the source's failure state."""
    run.items_posted = posted
    run.status = RunStatus.SUCCESS.value
    run.finished_at = int(time.time())

    source.last_run_at = run.finished_at
    source.last_error = None
    source.consecutive_failures = 0
    source.total_posts_created += posted

    db.commit()
    db.refresh(run)
