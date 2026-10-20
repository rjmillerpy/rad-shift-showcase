"""FastAPI dependencies that resolve the current user from the JWT.

    optional_user: the user, or None for an anonymous request
    required_user: the user, or 401 (no/expired token) / 404 (user gone)
    verified_user: required_user plus the email-verified gate (403)
    require_admin: 403 unless the user is an admin

Used by posts, profile and amble views; posts and profile each used to
carry their own copy (rule 2).
"""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.auth_jwt import AuthJWT, AuthJWTException
from app.common.db import get_db
from app.common.utils import get_user, require_verified


def optional_user(
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve the current user from the JWT if present, else None.

    Public-read endpoints use this dependency. Silence on `AuthJWTException` is
    intentional and documented — the endpoint is meant to work anonymously.
    """
    try:
        Authorize.jwt_optional()
        username = Authorize.get_jwt_subject()
    except AuthJWTException:
        return None
    if not username:
        return None
    return get_user(username, db)


def required_user(
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the current user or raise 401/404."""
    Authorize.jwt_required()
    user = get_user(Authorize.get_jwt_subject(), db)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def verified_user(user: User = Depends(required_user)) -> User:
    """Same as `required_user` but also enforces the email-verified gate."""
    require_verified(user)
    return user


def require_admin(user: User) -> None:
    """Raise 403 if the user is not an admin."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
