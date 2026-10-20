"""JWT access tokens for FastAPI routes.

Replaces fastapi-jwt-auth, which is unmaintained, crashes on import under
pydantic v2, and pins PyJWT < 2 (which has open security advisories). This is
the small subset of its API the app uses, with the same names, so views keep
declaring ``Authorize: AuthJWT = Depends()``:

    Authorize.jwt_required()      # 401 if no token, 422 if invalid
    Authorize.jwt_optional()      # anonymous if no token; still rejects bad ones
    Authorize.get_jwt_subject()   # the username, after one of the above
    AuthJWT().create_access_token(subject=username)

Tokens keep fastapi-jwt-auth's format (HS256; claims sub, iat, nbf, jti, exp,
type="access", fresh=False) and lifetime, so tokens issued before the switch
stay valid until they expire.

Errors: a missing or expired token is 401 (the frontend redirects to login on
401); a malformed header or an otherwise invalid token is 422. Clients get one
of the fixed messages below; why PyJWT rejected a token is logged, not returned.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any

import jwt
from fastapi import Request

from app.common.config import Config

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
# fastapi-jwt-auth's default lifetime, which the app always relied on.
ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
HEADER_NAME = "Authorization"
HEADER_TYPE = "Bearer"
ACCESS_TOKEN_TYPE = "access"  # nosec B105 - a token *type* label, not a secret

CLAIM_SUBJECT = "sub"
CLAIM_EXPIRES = "exp"
CLAIM_TYPE = "type"
# A token without these is rejected even if its signature is valid.
REQUIRED_CLAIMS = [CLAIM_EXPIRES, CLAIM_SUBJECT]

STATUS_UNAUTHENTICATED = HTTPStatus.UNAUTHORIZED  # 401: log in (again)
STATUS_INVALID = HTTPStatus.UNPROCESSABLE_ENTITY  # 422: the request itself is wrong

MISSING_HEADER_MESSAGE = f"Missing {HEADER_NAME} Header"
MISSING_TOKEN_MESSAGE = "Missing token"  # nosec B105 - an error message
BAD_HEADER_MESSAGE = f"Bad {HEADER_NAME} header. Expected value '{HEADER_TYPE} <JWT>'"
TOKEN_EXPIRED_MESSAGE = "Signature has expired"  # nosec B105 - an error message
INVALID_TOKEN_MESSAGE = "Invalid token"  # nosec B105 - an error message
ACCESS_TOKEN_REQUIRED_MESSAGE = "Only access tokens are allowed"  # nosec B105 - an error message


class AuthJWTException(Exception):
    """Base error; app.main turns these into JSON responses."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class MissingTokenError(AuthJWTException):
    pass


class InvalidHeaderError(AuthJWTException):
    pass


class JWTDecodeError(AuthJWTException):
    pass


class ExpiredTokenError(JWTDecodeError):
    pass


class AccessTokenRequired(AuthJWTException):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class AuthJWT:
    """Per-request JWT helper, injected with ``Depends()``."""

    def __init__(self, req: Request = None) -> None:  # type: ignore[assignment]
        # FastAPI passes the Request when used as a dependency; scripts and
        # tests construct it bare to mint or decode tokens.
        self._header: str | None = req.headers.get(HEADER_NAME) if req is not None else None
        self._token: str | None = None
        self._claims: dict[str, Any] | None = None

    # ── Issuing ───────────────────────────────────────────────────────────
    def create_access_token(self, subject: str, expires_time: timedelta | None = None) -> str:
        issued_at = _now()
        claims = {
            CLAIM_SUBJECT: subject,
            "iat": int(issued_at.timestamp()),
            "nbf": int(issued_at.timestamp()),
            "jti": str(uuid.uuid4()),
            CLAIM_EXPIRES: int((issued_at + (expires_time or ACCESS_TOKEN_EXPIRES)).timestamp()),
            CLAIM_TYPE: ACCESS_TOKEN_TYPE,
            "fresh": False,
        }
        return jwt.encode(claims, Config.JWT_SECRET_KEY, algorithm=ALGORITHM)

    # ── Verifying ─────────────────────────────────────────────────────────
    def jwt_required(self) -> None:
        """Require a valid access token in the Authorization header."""
        token = self._token_from_header()
        if token is None:
            raise MissingTokenError(STATUS_UNAUTHENTICATED, MISSING_HEADER_MESSAGE)
        self._claims = self._verified_access_claims(token)

    def jwt_optional(self) -> None:
        """Allow anonymous requests, but reject a token that is present and bad."""
        token = self._token_from_header()
        if token is not None:
            self._claims = self._verified_access_claims(token)

    def get_jwt_subject(self) -> str | None:
        """The username from the verified token, or None if there was none."""
        if self._claims is None:
            return None
        subject = self._claims.get(CLAIM_SUBJECT)
        return subject if isinstance(subject, str) else None

    def get_raw_jwt(self, encoded_token: str | None = None) -> dict[str, Any]:
        """Verify an access token passed in directly (e.g. an SSE query param)."""
        token = encoded_token or self._token
        if token is None:
            raise MissingTokenError(STATUS_UNAUTHENTICATED, MISSING_TOKEN_MESSAGE)
        return self._verified_access_claims(token)

    # ── Internals ─────────────────────────────────────────────────────────
    def _token_from_header(self) -> str | None:
        if self._header is None:
            return None
        parts = self._header.split()
        if len(parts) != 2 or parts[0] != HEADER_TYPE:
            raise InvalidHeaderError(STATUS_INVALID, BAD_HEADER_MESSAGE)
        self._token = parts[1]
        return self._token

    @staticmethod
    def _verified_access_claims(token: str) -> dict[str, Any]:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                Config.JWT_SECRET_KEY,
                # Pin the algorithm: never trust the token's own "alg" header.
                algorithms=[ALGORITHM],
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.ExpiredSignatureError as err:
            # Routine (tokens last 15 minutes), so not logged. 401 makes the
            # frontend send the user back to log in.
            raise ExpiredTokenError(STATUS_UNAUTHENTICATED, TOKEN_EXPIRED_MESSAGE) from err
        except jwt.InvalidTokenError as err:
            # Forged, truncated or malformed. Log why (never the token itself);
            # the client only learns that it was invalid.
            logger.warning("Rejected JWT: %s: %s", type(err).__name__, err)
            raise JWTDecodeError(STATUS_INVALID, INVALID_TOKEN_MESSAGE) from err
        if claims.get(CLAIM_TYPE) != ACCESS_TOKEN_TYPE:
            logger.warning("Rejected JWT: token type is not %r", ACCESS_TOKEN_TYPE)
            raise AccessTokenRequired(STATUS_INVALID, ACCESS_TOKEN_REQUIRED_MESSAGE)
        return claims
