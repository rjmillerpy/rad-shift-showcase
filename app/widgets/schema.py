from typing import Any

from pydantic import BaseModel, Field

from app.common.schema import FrozenModel

# Upper bound on sandbox telemetry events accepted in one request. A sandbox
# session produces at most a few hundred; this stops an unbounded payload.
MAX_TELEMETRY_EVENTS = 10_000


class WidgetCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    category: str = Field(
        ...,
        pattern="^(game|tool|api_connector|display_modifier|lambda|visualization|social|db_connector)$",
    )
    language: str = Field(
        ...,
        pattern="^(html|javascript|typescript|python|react|vue|angular|svelte|rust|golang|sql|nodejs|nextjs|c|cpp|csharp|ruby|php|fortran|basic|cobol|assembly|visual_basic)$",
    )

    # Multi-panel code
    code: str = Field(default="", max_length=500000)  # JS/logic panel
    html_panel: str | None = Field(None, max_length=200000)  # HTML panel
    css_panel: str | None = Field(None, max_length=100000)  # CSS panel
    compute_panel: str | None = Field(None, max_length=500000)  # Python/SQL compute panel
    compute_language: str | None = Field(None, pattern="^(python|sql)$")
    execution_mode: str = Field(default="client", pattern="^(client|server)$")

    # Keep existing fields
    css: str | None = Field(None, max_length=100000)  # backwards compat
    config: dict | None = None
    icon_emoji: str | None = None
    tags: list[str] | None = None
    permissions: list[str] | None = None
    default_width: int = Field(default=400, ge=200, le=1200)
    default_height: int = Field(default=300, ge=200, le=800)
    resizable: bool = False
    template_id: int | None = None  # If created from a template


class WidgetUpdateRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    code: str | None = Field(None, max_length=500000)
    html_panel: str | None = Field(None, max_length=200000)
    css_panel: str | None = Field(None, max_length=100000)
    compute_panel: str | None = Field(None, max_length=500000)
    compute_language: str | None = Field(None, pattern="^(python|sql)$")
    execution_mode: str | None = Field(None, pattern="^(client|server)$")
    css: str | None = Field(None, max_length=100000)
    config: dict | None = None
    icon_emoji: str | None = None
    tags: list[str] | None = None
    permissions: list[str] | None = None
    default_width: int | None = Field(None, ge=200, le=1200)
    default_height: int | None = Field(None, ge=200, le=800)
    resizable: bool | None = None


class WidgetSubmitRequest(BaseModel):
    widget_id: int


class WidgetReviewRequest(BaseModel):
    widget_id: int
    action: str = Field(..., pattern="^(approve|reject|suspend)$")
    notes: str | None = None


class WidgetRatingRequest(BaseModel):
    widget_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class WidgetExecuteRequest(BaseModel):
    code: str = Field(..., max_length=500000)
    language: str = Field(..., pattern="^(python|sql)$")
    input_data: str | None = None


class WidgetExecuteInstalledRequest(BaseModel):
    """Body for `POST /widgets/{widget_id}/execute` — the widget's own code is
    read from the DB, so only optional runtime input flows over the wire.

    `input_data` is deliberately `Any`: the executor accepts arbitrary JSON so
    widgets can define their own runtime-input shapes (this preserves the raw
    ``body: dict`` behavior the endpoint had before the Pydantic wrapping)."""

    input_data: Any | None = None


class TelemetryRequest(BaseModel):
    """Network/timer events captured by the sandbox page for one session."""

    events: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_TELEMETRY_EVENTS)


# ── Responses ──────────────────────────────────────────────────────────────


class WidgetOut(FrozenModel):
    """A widget as the API returns it (mirrors _WIDGET_FIELDS in service.py)."""

    id: int
    author_id: int
    author_username: str | None
    title: str
    description: str | None
    category: str
    language: str
    code: str
    html_panel: str | None
    css_panel: str | None
    compute_panel: str | None
    compute_language: str | None
    execution_mode: str
    html_output: str | None
    css: str | None
    config: dict[str, Any] | None
    version: str
    icon_emoji: str | None
    thumbnail_url: str | None
    tags: list[str] | None
    status: str
    review_notes: str | None
    reviewed_by: int | None
    reviewed_at: int | None
    security_score: int | None
    security_issues: list[Any] | None
    scan_passed: bool | None
    install_count: int
    likes: int
    saves: int
    shares: int
    permissions: list[str] | None
    default_width: int
    default_height: int
    resizable: bool
    created_at: int
    updated_at: int | None
    published_at: int | None


class WidgetResponse(FrozenModel):
    widget: WidgetOut


class WidgetListResponse(FrozenModel):
    widgets: list[WidgetOut]


class WidgetPageResponse(FrozenModel):
    widgets: list[WidgetOut]
    has_more: bool


class WidgetStatusResponse(FrozenModel):
    """Outcome of an action on one widget (delete, uninstall)."""

    status: str
    widget_id: int


class WidgetInstalledResponse(FrozenModel):
    status: str
    widget_id: int
    install_count: int


class WidgetRatingResponse(FrozenModel):
    status: str
    widget_id: int
    rating: int
    comment: str | None


class WidgetTemplate(FrozenModel):
    name: str
    description: str
    category: str
    language: str
    icon_emoji: str
    starter_code: str
    starter_css: str


class WidgetTemplatesResponse(FrozenModel):
    templates: list[WidgetTemplate]


class ExecutionResponse(FrozenModel):
    """Result of running a compute panel. Python runs report `stdout`, SQL
    runs report `results`; the endpoints serialise with exclude_unset so only
    the one that applies is present."""

    success: bool
    stderr: str
    duration_ms: int
    stdout: str | None = None
    results: list[dict[str, Any]] | None = None


class SandboxConfig(FrozenModel):
    browser: str
    os: str
    user_agent: str


class SandboxConfigsResponse(FrozenModel):
    configs: list[SandboxConfig]


class TelemetryAnalysis(FrozenModel):
    total_requests: int
    external_domains: list[str]
    suspicious_domains: list[str]
    websocket_connections: int
    service_workers: int
    timer_count: int
    risk_level: str
    risk_reasons: list[str]
    warnings: list[str]


class TelemetryResponse(FrozenModel):
    analysis: TelemetryAnalysis
    widget_id: int
