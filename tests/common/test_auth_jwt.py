"""Tests for app/common/auth_jwt.py, the in-house replacement for fastapi-jwt-auth."""

import os
import time
from datetime import timedelta

import jwt
import pytest
from starlette.requests import Request

from app.common.auth_jwt import (
    ACCESS_TOKEN_EXPIRES,
    AccessTokenRequired,
    AuthJWT,
    ExpiredTokenError,
    InvalidHeaderError,
    JWTDecodeError,
    MissingTokenError,
)

SECRET = os.environ["JWT_SECRET"]
WRONG_SECRET = "a-different-secret-also-32-bytes-long"


def _request(authorization: str | None) -> Request:
    """A real Starlette request carrying only the Authorization header."""
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def _with_header(value: str | None) -> AuthJWT:
    return AuthJWT(_request(value))


def _token(claims: dict, secret: str = SECRET) -> str:
    return jwt.encode(claims, secret, algorithm="HS256")


def _in_a_minute() -> int:
    return int(time.time()) + 60


class TestIssuing:
    def test_round_trip(self):
        token = AuthJWT().create_access_token(subject="alice")
        auth = _with_header(f"Bearer {token}")
        auth.jwt_required()
        assert auth.get_jwt_subject() == "alice"

    def test_claims_match_fastapi_jwt_auth_format(self):
        """Same claim set as the old library, so tokens issued before the switch keep working."""
        claims = jwt.decode(
            AuthJWT().create_access_token(subject="alice"), SECRET, algorithms=["HS256"]
        )
        assert set(claims) == {"sub", "iat", "nbf", "jti", "exp", "type", "fresh"}
        assert claims["type"] == "access" and claims["fresh"] is False

    def test_default_lifetime_is_unchanged(self):
        claims = jwt.decode(
            AuthJWT().create_access_token(subject="alice"), SECRET, algorithms=["HS256"]
        )
        assert claims["exp"] - claims["iat"] == int(ACCESS_TOKEN_EXPIRES.total_seconds())
        assert timedelta(minutes=15) == ACCESS_TOKEN_EXPIRES

    def test_legacy_token_shape_is_accepted(self):
        """A token shaped exactly like fastapi-jwt-auth's (hand-built) verifies."""
        now = int(time.time())
        legacy = jwt.encode(
            {
                "sub": "bob",
                "iat": now,
                "nbf": now,
                "jti": "x",
                "exp": now + 60,
                "type": "access",
                "fresh": False,
            },
            SECRET,
            algorithm="HS256",
        )
        auth = _with_header(f"Bearer {legacy}")
        auth.jwt_required()
        assert auth.get_jwt_subject() == "bob"


class TestRejecting:
    def test_missing_header_is_401(self):
        with pytest.raises(MissingTokenError) as exc:
            _with_header(None).jwt_required()
        assert exc.value.status_code == 401

    @pytest.mark.parametrize("header", ["Token abc", "Bearer", "Bearer a b", "abc"])
    def test_malformed_header_is_422(self, header):
        with pytest.raises(InvalidHeaderError) as exc:
            _with_header(header).jwt_required()
        assert exc.value.status_code == 422

    def test_expired_token_is_401_by_type_not_by_message(self):
        """401 is what sends the frontend to the login page. It comes from the
        exception itself; app.main no longer matches on PyJWT's wording."""
        token = AuthJWT().create_access_token(subject="alice", expires_time=timedelta(seconds=-1))
        with pytest.raises(ExpiredTokenError) as exc:
            _with_header(f"Bearer {token}").jwt_required()
        assert exc.value.status_code == 401
        assert exc.value.message == "Signature has expired"

    @pytest.mark.parametrize(
        "bad_token",
        [
            _token({"sub": "alice", "exp": _in_a_minute(), "type": "access"}, WRONG_SECRET),
            _token({"sub": "alice", "type": "access"}),
            _token({"exp": _in_a_minute(), "type": "access"}),
            "not.a.token",
            "garbage",
        ],
        ids=["wrong-secret", "no-expiry", "no-subject", "malformed", "not-a-jwt"],
    )
    def test_invalid_token_is_422_with_a_fixed_message(self, bad_token):
        """The client never sees why PyJWT rejected it (rule 10)."""
        with pytest.raises(JWTDecodeError) as exc:
            _with_header(f"Bearer {bad_token}").jwt_required()
        assert exc.value.status_code == 422
        assert exc.value.message == "Invalid token"

    def test_rejection_is_logged_with_the_reason_but_not_the_token(self, caplog):
        forged = _token({"sub": "alice", "exp": _in_a_minute(), "type": "access"}, WRONG_SECRET)
        with (
            caplog.at_level("WARNING", logger="app.common.auth_jwt"),
            pytest.raises(JWTDecodeError),
        ):
            _with_header(f"Bearer {forged}").jwt_required()
        assert "InvalidSignatureError" in caplog.text
        assert forged not in caplog.text

    def test_wrong_secret_is_rejected(self):
        forged = _token({"sub": "alice", "exp": _in_a_minute(), "type": "access"}, WRONG_SECRET)
        with pytest.raises(JWTDecodeError):
            _with_header(f"Bearer {forged}").jwt_required()

    def test_unsigned_alg_none_token_is_rejected(self):
        """The classic JWT attack: claim alg=none and drop the signature."""
        unsigned = jwt.encode(
            {"sub": "admin", "exp": int(time.time()) + 60, "type": "access"},
            key=None,
            algorithm="none",
        )
        with pytest.raises(JWTDecodeError):
            _with_header(f"Bearer {unsigned}").jwt_required()

    def test_non_access_token_is_rejected(self):
        """fastapi-jwt-auth's get_raw_jwt accepted refresh tokens; this doesn't."""
        refresh = jwt.encode(
            {"sub": "alice", "exp": int(time.time()) + 60, "type": "refresh"},
            SECRET,
            algorithm="HS256",
        )
        with pytest.raises(AccessTokenRequired):
            _with_header(f"Bearer {refresh}").jwt_required()
        with pytest.raises(AccessTokenRequired):
            AuthJWT().get_raw_jwt(refresh)

    def test_token_without_expiry_is_rejected(self):
        eternal = jwt.encode({"sub": "alice", "type": "access"}, SECRET, algorithm="HS256")
        with pytest.raises(JWTDecodeError):
            _with_header(f"Bearer {eternal}").jwt_required()


class TestRawToken:
    def test_no_token_anywhere_is_401(self):
        """get_raw_jwt with neither an argument nor a header-derived token."""
        with pytest.raises(MissingTokenError) as exc:
            AuthJWT().get_raw_jwt()
        assert exc.value.status_code == 401

    def test_returns_the_claims_of_a_valid_token(self):
        token = AuthJWT().create_access_token(subject="alice")
        assert AuthJWT().get_raw_jwt(token)["sub"] == "alice"


class TestOptional:
    def test_no_header_means_anonymous(self):
        auth = _with_header(None)
        auth.jwt_optional()
        assert auth.get_jwt_subject() is None

    def test_present_but_invalid_token_still_raises(self):
        with pytest.raises(JWTDecodeError):
            _with_header("Bearer not.a.token").jwt_optional()


class TestOverHttp:
    def test_protected_route_with_valid_token(self, client, create_user, auth_header):
        create_user(username="httpuser")
        resp = client.get("/auth/protected", headers=auth_header("httpuser"))
        assert resp.status_code == 200
        assert "httpuser" in resp.json()["message"]

    def test_expired_token_is_401_over_http(self, client, create_user):
        create_user(username="expired")
        token = AuthJWT().create_access_token(subject="expired", expires_time=timedelta(seconds=-1))
        resp = client.get("/auth/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Signature has expired"

    def test_missing_token_is_401_over_http(self, client):
        assert client.get("/auth/protected").status_code == 401
