"""Cross-domain helpers shared by multiple app packages.

Only the pieces that genuinely span domains live here. Anything domain-specific
belongs in its own package (rule 19).
"""

from fastapi import HTTPException
from sqlalchemy.orm import Query, Session

from app.auth.models import User
from app.common.constants import ACCOUNT_SUSPENDED_DETAIL


def get_user(username: str | None, db: Session) -> User | None:
    """Return the user with the given username, or None (also for no username)."""
    if not username:
        return None
    return db.query(User).filter_by(username=username).first()


def require_active(user: User) -> None:
    """Raise 403 if an admin has banned the user.

    Checked on every authenticated request, not only at login: a ban takes
    effect at once, even for a token issued before it.
    """
    if user.is_banned:
        raise HTTPException(status_code=403, detail=ACCOUNT_SUSPENDED_DETAIL)


def require_verified(user: User) -> None:
    """Raise 403 if the user's email is not verified."""
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address before performing this action.",
        )


def paginate[T](query: Query[T], offset: int, limit: int) -> tuple[list[T], bool]:
    """One page of `query` and whether another follows (fetches limit + 1 rows)."""
    rows = query.offset(offset).limit(limit + 1).all()
    return rows[:limit], len(rows) > limit
