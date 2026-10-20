"""Auth service — registration, email verification, login."""

import enum
import hmac
import logging
import os
import re
import secrets
import time

from sqlalchemy.orm import Session

from app.auth.constants import (
    ADMIN_SECRET_ENV_VAR,
    EMAIL_PATTERN,
    MAX_PASSWORD_BYTES,
    MAX_USERNAME_LEN,
    MIN_PASSWORD_LEN,
    MIN_USERNAME_LEN,
    USERNAME_PATTERN,
    VERIFICATION_TOKEN_BYTES,
    VERIFICATION_TOKEN_EXPIRY_SECONDS,
)
from app.auth.models import User
from app.auth.schema import AuthData
from app.avatar.generator import generate_avatar_url
from app.common.email import send_verification_email
from app.common.utils import get_user

logger = logging.getLogger(__name__)


_USERNAME_RE = re.compile(USERNAME_PATTERN)
_EMAIL_RE = re.compile(EMAIL_PATTERN)


def _generate_verification_token() -> str:
    return secrets.token_urlsafe(VERIFICATION_TOKEN_BYTES)


def _validate_credentials(username: str, password: str, email: str) -> str | None:
    """Return an error message if any credential is invalid, or None if all pass."""
    if not username or not (MIN_USERNAME_LEN <= len(username) <= MAX_USERNAME_LEN):
        return f"Username must be between {MIN_USERNAME_LEN} and {MAX_USERNAME_LEN} characters"
    if not _USERNAME_RE.match(username):
        return "Username may only contain letters, numbers, underscores, hyphens, and dots"
    if not password or len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters"
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return (
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            "(accented characters and emoji count as more than one)"
        )
    if not email or not _EMAIL_RE.match(email):
        return "A valid email address is required"
    return None


def _attach_avatar(user: User, db: Session) -> None:
    """Best-effort avatar generation. Failure is non-fatal — user gets default."""
    try:
        user.profile_picture_url = generate_avatar_url(user.username, user.email)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        # PIL / boto3 / network failures are all recoverable at this stage:
        # the user is already registered; a missing avatar is cosmetic.
        logger.warning("Avatar generation failed for %s: %s", user.username, exc)


def register_user(data: AuthData, db: Session) -> tuple[bool, str]:
    username = data.username
    password = data.password
    email = (data.email or "").strip()

    error = _validate_credentials(username, password, email)
    if error:
        return False, error

    if get_user(username, db):
        return False, "User already exists"
    if db.query(User).filter_by(email=email).first():
        return False, "Email already registered"

    token = _generate_verification_token()
    user = User(
        username=username,
        email=email,
        email_verified=False,
        verification_token=token,
        verification_token_expires=int(time.time()) + VERIFICATION_TOKEN_EXPIRY_SECONDS,
    )
    # nosemgrep: python.django.security.audit.unvalidated-password.unvalidated-password - checked above (MIN_PASSWORD_LEN); not Django
    user.set_password(password)

    db.add(user)
    db.commit()

    _attach_avatar(user, db)

    sent = send_verification_email(email, token)
    if not sent:
        logger.warning(
            "Verification email failed to send for user %s (%s); signup succeeded",
            username,
            email,
        )

    return True, "Success"


def verify_email(token: str, db: Session) -> tuple[bool, str]:
    user = db.query(User).filter_by(verification_token=token).first()
    if not user:
        return False, "Invalid verification token"

    if user.email_verified:
        return True, "Email already verified"

    if user.verification_token_expires and user.verification_token_expires < int(time.time()):
        return False, "Verification token has expired. Please request a new one."

    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.commit()
    return True, "Email verified successfully"


def resend_verification(username: str, db: Session) -> tuple[bool, str]:
    user = get_user(username, db)
    if not user:
        return False, "User not found"
    if user.email_verified:
        return False, "Email already verified"
    if not user.email:
        return False, "No email address on file"

    token = _generate_verification_token()
    user.verification_token = token
    user.verification_token_expires = int(time.time()) + VERIFICATION_TOKEN_EXPIRY_SECONDS
    db.commit()

    sent = send_verification_email(user.email, token)
    if not sent:
        logger.warning(
            "Resend verification email failed for user %s (%s)",
            username,
            user.email,
        )
        return False, "Failed to send verification email. Please try again shortly."

    return True, "Verification email sent"


def authenticate_user(data: AuthData, db: Session) -> User | None:
    user = get_user(data.username, db)
    if user and user.check_password(data.password):
        return user
    return None


class PromotionResult(enum.Enum):
    PROMOTED = "promoted"
    NOT_CONFIGURED = "not_configured"
    WRONG_SECRET = "wrong_secret"  # nosec B105 - an outcome label, not a secret
    USER_NOT_FOUND = "user_not_found"


def promote_to_admin(username: str | None, supplied_secret: str, db: Session) -> PromotionResult:
    """Make `username` an admin if `supplied_secret` matches ADMIN_SECRET.

    hmac.compare_digest takes the same time wherever the strings differ; a
    plain `==` returns at the first wrong character, so response timing would
    leak how much of a guess is right. Failed attempts are logged (never the
    supplied value) so guessing shows up in the logs.
    """
    expected = os.getenv(ADMIN_SECRET_ENV_VAR)
    if not expected:
        return PromotionResult.NOT_CONFIGURED
    if not hmac.compare_digest(supplied_secret.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("Rejected admin promotion attempt by user %r: wrong secret", username)
        return PromotionResult.WRONG_SECRET
    user = get_user(username, db)
    if not user:
        return PromotionResult.USER_NOT_FOUND
    user.is_admin = True
    db.commit()
    logger.info("User %r promoted to admin", username)
    return PromotionResult.PROMOTED
