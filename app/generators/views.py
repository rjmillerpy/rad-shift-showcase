"""Admin-only API endpoints for the content generator system."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.auth_jwt import AuthJWT
from app.common.db import get_db
from app.common.deps import require_admin
from app.common.schema import StatusResponse
from app.common.utils import get_user

from . import service
from .constants import (
    DEFAULT_BROWSER_ENGINE,
    DEFAULT_LIST_LIMIT,
    DEFAULT_RUN_LIMIT,
    MAX_LIST_LIMIT,
    MAX_RUN_LIMIT,
)
from .models import GeneratorProfile, GeneratorRun, GeneratorSource
from .schema import (
    AnalyzeRequest,
    GeneratorProfileResponse,
    GeneratorProfilesResponse,
    GeneratorRunResponse,
    GeneratorRunsResponse,
    GeneratorSourceResponse,
    GeneratorSourcesResponse,
    ProfileCreateRequest,
    RunSourceRequest,
    SelectorsResponse,
    SelectorsSavedResponse,
    SourceCreateRequest,
    SourceUpdateRequest,
)
from .web import web_scraper

logger = logging.getLogger(__name__)

generator_router = APIRouter()


def _get_admin_user(authorize: AuthJWT, db: Session) -> User:
    """Authenticate and verify admin access."""
    authorize.jwt_required()
    user = get_user(authorize.get_jwt_subject(), db)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    require_admin(user)
    return user


# ── Sources ──────────────────────────────────────────────────────────


@generator_router.get("/sources")
def list_sources(
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorSourcesResponse:
    _get_admin_user(Authorize, db)
    sources = service.list_sources(db, offset=offset, limit=limit)
    return GeneratorSourcesResponse.model_validate(
        {"sources": [_serialize_source(s) for s in sources]}
    )


@generator_router.get("/sources/{source_id}")
def get_source(
    source_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorSourceResponse:
    _get_admin_user(Authorize, db)
    source = service.get_source(source_id, db)
    return GeneratorSourceResponse.model_validate({"source": _serialize_source(source)})


@generator_router.post("/sources")
def create_source(
    payload: SourceCreateRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorSourceResponse:
    _get_admin_user(Authorize, db)
    source = service.create_source(
        name=payload.name,
        site_url=payload.site_url,
        db=db,
        description=payload.description,
        config=payload.config.model_dump() if payload.config else None,
        run_interval_minutes=payload.run_interval_minutes,
        platform=payload.platform,
        platform_config=payload.platform_config,
    )
    return GeneratorSourceResponse.model_validate({"source": _serialize_source(source)})


@generator_router.put("/sources/{source_id}")
def update_source(
    source_id: int,
    payload: SourceUpdateRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorSourceResponse:
    _get_admin_user(Authorize, db)
    source = service.update_source(source_id, payload, db)
    return GeneratorSourceResponse.model_validate({"source": _serialize_source(source)})


@generator_router.delete("/sources/{source_id}")
def delete_source(
    source_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> StatusResponse:
    _get_admin_user(Authorize, db)
    service.delete_source(source_id, db)
    return StatusResponse(status="deleted")


# ── Profiles ─────────────────────────────────────────────────────────


@generator_router.get("/sources/{source_id}/profiles")
def list_profiles(
    source_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorProfilesResponse:
    _get_admin_user(Authorize, db)
    profiles = service.list_profiles(source_id, db)
    return GeneratorProfilesResponse.model_validate(
        {"profiles": [_serialize_profile(p) for p in profiles]}
    )


@generator_router.post("/profiles")
def attach_profile(
    payload: ProfileCreateRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorProfileResponse:
    _get_admin_user(Authorize, db)
    profile = service.attach_profile(payload.source_id, payload.user_id, db)
    return GeneratorProfileResponse.model_validate({"profile": _serialize_profile(profile)})


@generator_router.delete("/profiles/{profile_id}")
def detach_profile(
    profile_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> StatusResponse:
    _get_admin_user(Authorize, db)
    service.detach_profile(profile_id, db)
    return StatusResponse(status="detached")


# ── Runs ─────────────────────────────────────────────────────────────


@generator_router.get("/sources/{source_id}/runs")
def list_runs(
    source_id: int,
    limit: int = Query(DEFAULT_RUN_LIMIT, ge=1, le=MAX_RUN_LIMIT),
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorRunsResponse:
    _get_admin_user(Authorize, db)
    runs = service.list_runs(source_id, db, limit=limit)
    return GeneratorRunsResponse.model_validate({"runs": [_serialize_run(r) for r in runs]})


@generator_router.post("/run")
def run_scraper(
    payload: RunSourceRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> GeneratorRunResponse:
    _get_admin_user(Authorize, db)
    run = service.run_scraper(payload.source_id, db)
    return GeneratorRunResponse.model_validate({"run": _serialize_run(run)})


# ── AI Analysis ──────────────────────────────────────────────────────


@generator_router.post("/analyze")
def analyze_site(
    payload: AnalyzeRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> SelectorsResponse:
    _get_admin_user(Authorize, db)
    selectors = web_scraper().analyze_page(
        payload.site_url,
        payload.content_hint or "",
        use_browser=True,
        browser_engine=payload.browser_engine,
    )
    return SelectorsResponse.model_validate({"selectors": selectors})


# ── Serializers ──────────────────────────────────────────────────────


@generator_router.post("/sources/{source_id}/analyze")
def analyze_and_save(
    source_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> SelectorsSavedResponse:
    """Analyze the source URL and save the generated selectors."""
    _get_admin_user(Authorize, db)
    source = service.get_source(source_id, db)
    config: dict[str, Any] = source.config or {}
    selectors = web_scraper().analyze_page(
        source.site_url,
        config.get("content_hint", source.description or ""),
        use_browser=config.get("use_browser", False),
        browser_engine=config.get("browser_engine", DEFAULT_BROWSER_ENGINE),
    )
    source.selectors = selectors
    db.commit()
    return SelectorsSavedResponse.model_validate({"selectors": selectors, "status": "saved"})


def _serialize_source(s: GeneratorSource) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "site_url": s.site_url,
        "description": s.description,
        "platform": s.platform,
        "platform_config": s.platform_config,
        "selectors": s.selectors,
        "config": s.config,
        "is_active": s.is_active,
        "last_run_at": s.last_run_at,
        "last_error": s.last_error,
        "total_posts_created": s.total_posts_created,
        "consecutive_failures": s.consecutive_failures,
        "run_interval_minutes": s.run_interval_minutes,
        "profile_count": len(s.profiles) if s.profiles else 0,
    }


def _serialize_profile(p: GeneratorProfile) -> dict:
    return {
        "id": p.id,
        "source_id": p.source_id,
        "user_id": p.user_id,
        "username": p.user.username if p.user else None,
        "is_active": p.is_active,
    }


def _serialize_run(r: GeneratorRun) -> dict:
    return {
        "id": r.id,
        "source_id": r.source_id,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "status": r.status,
        "items_found": r.items_found,
        "items_posted": r.items_posted,
        "error_message": r.error_message,
        "selectors_updated": r.selectors_updated,
    }
