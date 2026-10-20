"""Constants for the Amble content sub-domain.

One source of truth (rules 8, 16) — YAML config filename, page-size bounds,
log-event names, and user-facing error strings all live here so the loader,
service, views, and tests never disagree.
"""

from pathlib import Path

# ── YAML config file ────────────────────────────────────────────────────────
# Which file is read is the edition's choice (app/plugins.py): production's
# town is private, and the public edition reads the demo town's bindings,
# which live next to this module.
DEMO_BINDINGS_PATH: Path = Path(__file__).parent / "demo-bindings.yaml"

# ── Response page size ─────────────────────────────────────────────────────
# The dialogue frame shows one post at a time (Phase 1.4a UX), so we return a
# small window and let the client advance the cursor. Server-side we still
# hit feeds.py which uses limit+1 has_more, so a low limit here keeps the
# query cheap.
DEFAULT_PAGE_LIMIT: int = 5
MAX_PAGE_LIMIT: int = 20

# ── Log-event names ─────────────────────────────────────────────────────────
LOG_EVENT_FETCH: str = "amble.content.fetch"
LOG_EVENT_FETCH_UNKNOWN_ENTITY: str = "amble.content.fetch.unknown_entity"
LOG_EVENT_BINDINGS_LOADED: str = "amble.content.bindings_loaded"
LOG_EVENT_BINDINGS_ERROR: str = "amble.content.bindings_error"

# ── User-facing error strings ───────────────────────────────────────────────
ERROR_MESSAGE_UNKNOWN_ENTITY: str = "Unknown entity"
ERROR_MESSAGE_BAD_CURSOR: str = "Invalid cursor"

# ── Phase 2.3b freshness ────────────────────────────────────────────────────
# When `freshness_bias > 0`, posts older than this many seconds get a
# ranking penalty proportional to the bias. 30 days is the neighbourhood
# feed's practical "old" — matches the roadmap example of newsstands
# and community boards preferring the last month of activity.
FRESHNESS_STALE_SECONDS: int = 60 * 60 * 24 * 30

# ── Phase 2.3c follow-graph boost ───────────────────────────────────────────
# Followed authors' posts sort BEFORE non-followed authors' when
# `personalise_by_follow=True`. Concrete unit picked so the ranking key
# always dominates any real timestamp value (unix seconds fit comfortably
# in int32).
FOLLOW_BOOST_RANK: int = 10_000_000_000
