"""Rate-limit policies: how many requests a client may make per window.

Counters live in Postgres (app/ratelimit/service.py), so every API replica
shares them: per-process counters would let a client make the limit times
the number of replicas.
"""

from dataclasses import dataclass

# Off only when this is "false" (any case): tests, or an emergency.
RATE_LIMITS_ENABLED_ENV_VAR = "RATE_LIMITS_ENABLED"
# Counter rows older than this are deleted as new windows open.
STALE_WINDOW_SECONDS = 24 * 3600

MINUTE = 60
HOUR = 3600


@dataclass(frozen=True)
class Policy:
    name: str
    limit: int
    window_seconds: int
    # True: keyed by the signed-in user (else the IP). False: always the IP,
    # for paths used before signing in.
    per_user: bool


LOGIN = Policy("login", limit=10, window_seconds=MINUTE, per_user=False)
PROMOTE_ADMIN = Policy("promote-admin", limit=5, window_seconds=HOUR, per_user=False)
SIGNUP = Policy("signup", limit=5, window_seconds=HOUR, per_user=False)
RESEND_VERIFICATION = Policy("resend-verification", limit=3, window_seconds=HOUR, per_user=False)
# A game may save often (radshift.storage).
WIDGET_STORAGE = Policy("widget-storage", limit=300, window_seconds=MINUTE, per_user=True)
WRITE = Policy("write", limit=60, window_seconds=MINUTE, per_user=True)

# (method, route template) -> policy; any other write gets WRITE, reads none.
ROUTE_POLICIES: dict[tuple[str, str], Policy] = {
    ("POST", "/auth/login"): LOGIN,
    ("POST", "/auth/promote-admin"): PROMOTE_ADMIN,
    ("POST", "/auth/signup"): SIGNUP,
    ("POST", "/auth/resend-verification"): RESEND_VERIFICATION,
    ("PUT", "/widgets/{widget_id}/storage/{key}"): WIDGET_STORAGE,
    ("DELETE", "/widgets/{widget_id}/storage/{key}"): WIDGET_STORAGE,
}
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
