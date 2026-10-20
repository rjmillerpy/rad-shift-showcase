"""Widget API endpoints."""

import contextlib
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.auth_jwt import AuthJWT, AuthJWTException
from app.common.db import get_db
from app.common.deps import require_admin
from app.common.utils import get_user
from app.flags.constants import Flag
from app.flags.service import is_enabled
from app.widgets.compiler import compile_multi_panel, compile_to_html
from app.widgets.executor import execute_python, execute_sql
from app.widgets.schema import (
    ExecutionResponse,
    SandboxConfigsResponse,
    TelemetryRequest,
    TelemetryResponse,
    WidgetCreateRequest,
    WidgetExecuteInstalledRequest,
    WidgetExecuteRequest,
    WidgetInstalledResponse,
    WidgetListResponse,
    WidgetOut,
    WidgetPageResponse,
    WidgetRatingRequest,
    WidgetRatingResponse,
    WidgetResponse,
    WidgetReviewRequest,
    WidgetStatusResponse,
    WidgetSubmitRequest,
    WidgetTemplatesResponse,
    WidgetUpdateRequest,
)
from app.widgets.service import (
    create_widget,
    delete_widget,
    get_installed_widgets,
    get_widget,
    install_widget,
    list_my_widgets,
    list_widgets,
    rate_widget,
    review_widget,
    submit_for_review,
    uninstall_widget,
    update_widget,
)
from app.widgets.templates import BUILTIN_TEMPLATES

widget_router = APIRouter()


def _require_user(Authorize: AuthJWT, db: Session) -> User:
    """Extract and validate the authenticated user."""
    Authorize.jwt_required()
    user = get_user(Authorize.get_jwt_subject(), db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# -- Public (optional auth) ------------------------------------------------


@widget_router.get("/browse")
def browse_widgets(
    category: str | None = None,
    offset: int = 0,
    limit: int = 20,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetPageResponse:
    # /browse is public-read; a malformed token shouldn't block anon access.
    with contextlib.suppress(AuthJWTException):
        Authorize.jwt_optional()
    widgets, has_more = list_widgets(
        db, status="approved", category=category, offset=offset, limit=limit
    )
    return WidgetPageResponse.model_validate({"widgets": widgets, "has_more": has_more})


@widget_router.get("/templates")
def list_templates() -> WidgetTemplatesResponse:
    return WidgetTemplatesResponse.model_validate({"templates": BUILTIN_TEMPLATES})


# -- Authenticated ----------------------------------------------------------


@widget_router.get("/my")
def my_widgets(Authorize: AuthJWT = Depends(), db: Session = Depends(get_db)) -> WidgetListResponse:
    user = _require_user(Authorize, db)
    return WidgetListResponse.model_validate({"widgets": list_my_widgets(user, db)})


@widget_router.get("/installed")
def installed_widgets(
    Authorize: AuthJWT = Depends(), db: Session = Depends(get_db)
) -> WidgetListResponse:
    user = _require_user(Authorize, db)
    return WidgetListResponse.model_validate({"widgets": get_installed_widgets(user, db)})


@widget_router.post("/create")
def create_widget_view(
    payload: WidgetCreateRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetOut:
    user = _require_user(Authorize, db)
    return WidgetOut.model_validate(create_widget(user, payload.model_dump(), db))


@widget_router.post("/submit")
def submit_widget_view(
    payload: WidgetSubmitRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetOut:
    user = _require_user(Authorize, db)
    return WidgetOut.model_validate(submit_for_review(user, payload.widget_id, db))


@widget_router.post("/rate")
def rate_widget_view(
    payload: WidgetRatingRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetRatingResponse:
    user = _require_user(Authorize, db)
    return WidgetRatingResponse.model_validate(
        rate_widget(user, payload.widget_id, payload.rating, payload.comment, db)
    )


@widget_router.post("/install/{widget_id}")
def install_widget_view(
    widget_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetInstalledResponse:
    user = _require_user(Authorize, db)
    return WidgetInstalledResponse.model_validate(install_widget(user, widget_id, db))


@widget_router.delete("/install/{widget_id}")
def uninstall_widget_view(
    widget_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetStatusResponse:
    user = _require_user(Authorize, db)
    return WidgetStatusResponse.model_validate(uninstall_widget(user, widget_id, db))


# -- Server-side execution --------------------------------------------------
#
# The executor is not a real sandbox (see app/widgets/executor.py), so running
# arbitrary code is off unless the operator opts in, and even then admin-only.
# Two switches, both must be on: the env var is the deploy-time ceiling, the
# widget-server-execution flag the runtime kill switch (off within seconds,
# no redeploy; app/flags/).

SERVER_EXECUTION_ENV_VAR = "WIDGET_SERVER_EXECUTION_ENABLED"


def _require_execution_allowed(Authorize: AuthJWT, db: Session) -> None:
    """401 unauthenticated, 503 when disabled, 403 for non-admins."""
    user = _require_user(Authorize, db)
    if os.getenv(SERVER_EXECUTION_ENV_VAR, "").lower() != "true" or not is_enabled(
        Flag.WIDGET_SERVER_EXECUTION, user
    ):
        raise HTTPException(
            status_code=503,
            detail="Server-side widget execution is disabled",
        )
    require_admin(user)


@widget_router.post("/execute", response_model_exclude_unset=True)
def execute_code(
    body: WidgetExecuteRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> ExecutionResponse:
    """Execute code server-side for preview. Python and SQL only."""
    _require_execution_allowed(Authorize, db)
    if body.language == "python":
        return ExecutionResponse.model_validate(
            execute_python(body.code, input_data=body.input_data)
        )
    elif body.language == "sql":
        return ExecutionResponse.model_validate(execute_sql(body.code))
    raise HTTPException(status_code=400, detail="Unsupported language")


@widget_router.post("/{widget_id}/execute", response_model_exclude_unset=True)
def execute_widget(
    widget_id: int,
    body: WidgetExecuteInstalledRequest | None = None,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> ExecutionResponse:
    """Execute a widget's compute panel server-side. Returns stdout/stderr."""
    body = body or WidgetExecuteInstalledRequest()  # fresh per request, not a shared default
    _require_execution_allowed(Authorize, db)
    widget = get_widget(widget_id, db)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    compute_panel = widget.get("compute_panel")
    compute_language = widget.get("compute_language")
    if not compute_panel or not compute_language:
        raise HTTPException(status_code=400, detail="Widget has no compute panel")
    if widget.get("execution_mode") != "server":
        raise HTTPException(status_code=400, detail="Widget is not configured for server execution")
    if compute_language == "python":
        return ExecutionResponse.model_validate(
            execute_python(compute_panel, input_data=body.input_data)
        )
    if compute_language == "sql":
        return ExecutionResponse.model_validate(execute_sql(compute_panel))
    raise HTTPException(status_code=400, detail="Unsupported compute language")


# -- Admin only -------------------------------------------------------------


@widget_router.get("/pending")
def pending_widgets(
    Authorize: AuthJWT = Depends(), db: Session = Depends(get_db)
) -> WidgetPageResponse:
    user = _require_user(Authorize, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    widgets, has_more = list_widgets(db, status="submitted")
    return WidgetPageResponse.model_validate({"widgets": widgets, "has_more": has_more})


@widget_router.post("/review")
def review_widget_view(
    payload: WidgetReviewRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetOut:
    user = _require_user(Authorize, db)
    return WidgetOut.model_validate(
        review_widget(user, payload.widget_id, payload.action, payload.notes, db)
    )


# -- Sandbox / Quarantine ---------------------------------------------------


@widget_router.get("/sandbox/configs")
def get_sandbox_configs_endpoint() -> SandboxConfigsResponse:
    """List available browser/OS configurations for sandbox testing."""
    from app.widgets.sandbox import get_sandbox_configs

    return SandboxConfigsResponse.model_validate({"configs": get_sandbox_configs()})


@widget_router.get("/{widget_id}/sandbox", response_class=HTMLResponse)
def get_sandbox_render(
    widget_id: int, config_idx: int = 0, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Render widget in quarantine mode with monitoring."""
    from app.widgets.sandbox import wrap_in_quarantine

    widget_data = get_widget(widget_id, db)
    if not widget_data:
        return HTMLResponse("<p>Widget not found</p>", status_code=404)
    html = widget_data.get("html_output") or widget_data.get("code", "")
    quarantined = wrap_in_quarantine(html, widget_id)
    return HTMLResponse(quarantined)


@widget_router.post("/{widget_id}/sandbox/telemetry")
def submit_telemetry(
    widget_id: int,
    telemetry: TelemetryRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> TelemetryResponse:
    """Submit captured telemetry from a sandbox session for analysis."""
    from app.widgets.sandbox import analyze_telemetry

    Authorize.jwt_required()
    analysis = analyze_telemetry(telemetry.events)
    return TelemetryResponse.model_validate({"analysis": analysis, "widget_id": widget_id})


# -- Parameterized routes (after fixed paths to avoid conflicts) ------------


@widget_router.get("/{widget_id}")
def get_widget_view(
    widget_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetResponse:
    # /{widget_id} is public-read; a malformed token shouldn't block anon access.
    with contextlib.suppress(AuthJWTException):
        Authorize.jwt_optional()
    widget = get_widget(widget_id, db)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    return WidgetResponse.model_validate({"widget": widget})


@widget_router.put("/{widget_id}")
def update_widget_view(
    widget_id: int,
    payload: WidgetUpdateRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetOut:
    user = _require_user(Authorize, db)
    return WidgetOut.model_validate(
        update_widget(user, widget_id, payload.model_dump(exclude_unset=True), db)
    )


@widget_router.delete("/{widget_id}")
def delete_widget_view(
    widget_id: int,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> WidgetStatusResponse:
    user = _require_user(Authorize, db)
    return WidgetStatusResponse.model_validate(delete_widget(user, widget_id, db))


@widget_router.get("/{widget_id}/render", response_class=HTMLResponse)
def render_widget(widget_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    widget = get_widget(widget_id, db)
    if not widget or widget["status"] != "approved":
        return HTMLResponse("<p>Widget not available</p>", status_code=404)
    # Use pre-compiled html_output when available; otherwise compile on the fly
    html = widget.get("html_output")
    if not html:
        # Try multi-panel compilation if panels are present
        if widget.get("html_panel") or widget.get("css_panel") or widget.get("compute_panel"):
            html = compile_multi_panel(
                html_panel=widget.get("html_panel", ""),
                css_panel=widget.get("css_panel", ""),
                js_code=widget.get("code", ""),
                compute_panel=widget.get("compute_panel"),
                compute_language=widget.get("compute_language"),
            )
        else:
            html = compile_to_html(
                widget.get("code", ""),
                widget.get("language", "html"),
                css=widget.get("css"),
            )
    return HTMLResponse(html)
