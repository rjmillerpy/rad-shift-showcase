"""Constants for the Amble avatar sub-domain.

Kept in one place so the Pydantic schema, service, and tests never disagree
on the allowed attribute lengths or the wire-shape of the response payload
(rules 8 and 16).
"""

# ── Field length bounds (Pydantic + DB enforce the same numbers) ────────────
MIN_ATTRIBUTE_LENGTH: int = 1
MAX_ATTRIBUTE_LENGTH: int = 32

# ── Allowed literal values ──────────────────────────────────────────────────
ALLOWED_GENDERS: tuple[str, ...] = ("boy", "girl")

# ── Log-event names (rule 41 — observable, structured) ─────────────────────
LOG_EVENT_READ: str = "amble.avatar.read"
LOG_EVENT_UPSERT: str = "amble.avatar.upsert"
LOG_EVENT_UPSERT_FAILED: str = "amble.avatar.upsert.failed"

# ── User-facing error strings (never leak internal detail, rule 10) ────────
ERROR_MESSAGE_PERSISTENCE: str = "Could not save avatar"
