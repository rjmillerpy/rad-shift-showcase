"""Count a request against a policy's window; say whether it may go ahead.

A fixed window: requests are counted per key in each window_seconds slot,
with one atomic upsert per request (INSERT ... ON CONFLICT DO UPDATE ...
RETURNING), so concurrent requests on several replicas can't both slip
under the limit. When a key opens a new window, its older rows and any row
older than a day are deleted, so the table stays about one row per active
client.
"""

import os
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.ratelimit.constants import RATE_LIMITS_ENABLED_ENV_VAR, STALE_WINDOW_SECONDS, Policy
from app.ratelimit.models import RateLimitWindow


@dataclass(frozen=True)
class Decision:
    allowed: bool
    # Seconds until the window resets (Retry-After); 0 when allowed.
    retry_after: int


def rate_limits_enabled() -> bool:
    return os.getenv(RATE_LIMITS_ENABLED_ENV_VAR, "true").lower() != "false"


def _insert(db: Session):
    dialect = db.get_bind().dialect.name
    return (postgresql if dialect == "postgresql" else sqlite).insert(RateLimitWindow)


def hit(db: Session, policy: Policy, identity: str, now: int) -> Decision:
    """Count one request by `identity` ("user:alice", "ip:1.2.3.4") under `policy`."""
    key = f"{policy.name}:{identity}"
    window_start = now - now % policy.window_seconds
    statement = (
        _insert(db)
        .values(key=key, window_start=window_start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitWindow.key, RateLimitWindow.window_start],
            set_={"count": RateLimitWindow.count + 1},
        )
        .returning(RateLimitWindow.count)
    )
    count = db.execute(statement).scalar_one()
    if count == 1:  # this request opened a new window: tidy up
        db.execute(
            delete(RateLimitWindow).where(
                (RateLimitWindow.key == key) & (RateLimitWindow.window_start < window_start)
                | (RateLimitWindow.window_start < now - STALE_WINDOW_SECONDS)
            )
        )
    db.commit()
    if count <= policy.limit:
        return Decision(allowed=True, retry_after=0)
    return Decision(allowed=False, retry_after=window_start + policy.window_seconds - now)
