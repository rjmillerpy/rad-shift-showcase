"""Pydantic schemas for the Amble content endpoint (Phase 1.4b).

Wire shape mirrors the frontend `AmbleContentResponse`/`AmblePost`
schemas defined in `src/app/amble/data/schema.ts`. Any change here has to
land on both sides — the frontend Zod parse would blow up on drift, which
is a feature (rule 5 boundary).
"""

from typing import Annotated, Literal

from pydantic import Field

from app.common.schema import FrozenModel


# ── Binding kinds (config-file shape) ──────────────────────────────────────
# These are the shapes the YAML author writes. Loaded once at startup and
# stored in-memory (see bindings.py). Blended sums weighted parts —
# preserves CONTENT-03 serendipity (one entity can lean multiple ways).
class PersistentIdentityBinding(FrozenModel):
    kind: Literal["persistent-identity"]
    usernames: list[str] = Field(min_length=1)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class CategoryBinding(FrozenModel):
    kind: Literal["category"]
    tags: list[str] = Field(min_length=1)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


# Unions are discriminated on `kind`: pydantic picks the model by that field
# instead of trying each one, and errors name the bad `kind` directly.
BindingPart = Annotated[PersistentIdentityBinding | CategoryBinding, Field(discriminator="kind")]


class BlendedBinding(FrozenModel):
    kind: Literal["blended"]
    parts: list[BindingPart] = Field(min_length=1)


Binding = Annotated[
    PersistentIdentityBinding | CategoryBinding | BlendedBinding, Field(discriminator="kind")
]


class EntityConfig(FrozenModel):
    entity_id: str = Field(min_length=1, max_length=64)
    binding: Binding
    # Optional custom empty-state string for CONTENT-05 fallback. Defaults
    # live on the frontend per-type; setting one here overrides per-entity.
    empty_state_text: str | None = None
    # Phase 2.3b — freshness bias. 0.0 = pure recency-desc (default).
    # 1.0 = ordering deprioritises anything older than
    # FRESHNESS_STALE_SECONDS. Values in between mix. Newsstands /
    # community boards should set ~0.8; historical anchors (antique
    # shop, library) stay at 0.
    freshness_bias: float = Field(default=0.0, ge=0.0, le=1.0)
    # Phase 2.3c — follow-graph personalisation. When true, posts from
    # accounts the viewer follows get boosted to the front of the
    # binding's matched set. Defaults off — most anchors surface the
    # generic feed regardless of who's watching.
    personalise_by_follow: bool = False


# ── Wire response shape ─────────────────────────────────────────────────────
class AmblePost(FrozenModel):
    id: int
    author: str
    text: str
    unix_timestamp: int
    # Engagement fields (Phase 1.5, ENGAGE-01/02). Counts come from the
    # PostResponse the feeds layer already builds; per-viewer flags let the
    # dialogue action bar render like/repost buttons in the right initial
    # state. Adding a field here needs matching change in the frontend Zod
    # schema (`data/schema.ts`), which the boundary Zod parse enforces.
    likes: int = 0
    reposts: int = 0
    saves: int = 0
    liked_by_me: bool = False
    reposted_by_me: bool = False


class AmbleContentResponse(FrozenModel):
    entity_id: str
    posts: list[AmblePost]
    next_cursor: str | None = None
    empty: bool
