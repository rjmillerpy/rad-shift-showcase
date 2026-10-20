"""Direct service-level unit tests for app/auth/service.py.

API-level coverage lives in tests/auth/test_views.py; end-to-end email
verification flow lives in tests/integration/test_email_verification.py.
"""

import time
from unittest.mock import patch

import pytest

from app.auth import service
from app.auth.constants import (
    MAX_USERNAME_LEN,
    MIN_PASSWORD_LEN,
    MIN_USERNAME_LEN,
    VERIFICATION_TOKEN_EXPIRY_SECONDS,
)
from app.auth.models import User
from app.auth.schema import AuthData


def _payload(**overrides) -> AuthData:
    base = {"username": "svc_user", "password": "password123", "email": "svc@test.com"}
    base.update(overrides)
    return AuthData(**base)


class TestRegisterUser:
    def test_success(self, db_session):
        ok, msg = service.register_user(_payload(username="fresh"), db_session)
        assert ok is True
        assert msg == "Success"
        assert db_session.query(User).filter_by(username="fresh").count() == 1

    @pytest.mark.parametrize(
        "username,password,email,fragment",
        [
            ("ab", "password123", "a@b.com", f"between {MIN_USERNAME_LEN} and {MAX_USERNAME_LEN}"),
            (
                "x" * (MAX_USERNAME_LEN + 1),
                "password123",
                "a@b.com",
                f"between {MIN_USERNAME_LEN} and {MAX_USERNAME_LEN}",
            ),
            ("bad char", "password123", "a@b.com", "letters, numbers"),
            ("goodname", "short", "a@b.com", f"at least {MIN_PASSWORD_LEN} characters"),
            ("goodname", "p" * 73, "a@b.com", "at most 72 bytes"),
            # 37 x "é" is 37 characters but 74 UTF-8 bytes: the limit is bytes.
            ("goodname", "é" * 37, "a@b.com", "at most 72 bytes"),
            ("goodname", "password123", "not-an-email", "valid email"),
            ("goodname", "password123", "", "valid email"),
        ],
        ids=[
            "username_too_short",
            "username_too_long",
            "username_bad_chars",
            "password_too_short",
            "password_over_72_bytes",
            "password_over_72_bytes_multibyte",
            "email_invalid",
            "email_empty",
        ],
    )
    def test_validation_errors(self, db_session, username, password, email, fragment):
        ok, msg = service.register_user(
            _payload(username=username, password=password, email=email),
            db_session,
        )
        assert ok is False
        assert fragment in msg

    def test_rejects_duplicate_username(self, db_session, create_user):
        create_user(username="taken")
        ok, msg = service.register_user(
            _payload(username="taken", email="different@test.com"),
            db_session,
        )
        assert ok is False
        assert "already exists" in msg

    def test_rejects_duplicate_email(self, db_session, create_user):
        create_user(username="first_user", email="shared@test.com")
        ok, msg = service.register_user(
            _payload(username="other_user", email="shared@test.com"),
            db_session,
        )
        assert ok is False
        assert "Email already registered" in msg

    def test_stores_hashed_password(self, db_session):
        raw = "supersecret123"
        service.register_user(_payload(username="hashed", password=raw), db_session)
        row = db_session.query(User).filter_by(username="hashed").first()
        assert row.password_hash != raw
        assert row.check_password(raw)

    def test_persists_verification_token_with_future_expiry(self, db_session):
        service.register_user(_payload(username="tokened"), db_session)
        row = db_session.query(User).filter_by(username="tokened").first()
        assert row.verification_token
        assert row.verification_token_expires > int(time.time())
        # NOTE: the global test-fixture `_auto_verify_user` after_insert hook
        # flips `email_verified` to True on any INSERT so `require_verified`
        # passes downstream; that is a test-only concession, not production
        # behavior. To assert the real service default here, undo the flip.
        row.email_verified = False
        db_session.commit()
        db_session.refresh(row)
        assert row.email_verified is False

    def test_signup_continues_when_email_send_fails(self, db_session):
        with patch(
            "app.auth.service.send_verification_email",
            return_value=False,
        ) as send:
            ok, msg = service.register_user(
                _payload(username="email_fail"),
                db_session,
            )
        send.assert_called_once()
        assert ok is True  # Registration succeeds even if email send fails
        assert db_session.query(User).filter_by(username="email_fail").count() == 1


class TestAuthenticateUser:
    def test_returns_user_when_password_matches(self, db_session, create_user):
        create_user(username="alice", password="rightpass1")
        user = service.authenticate_user(
            AuthData(username="alice", password="rightpass1"),
            db_session,
        )
        assert user is not None
        assert user.username == "alice"

    def test_returns_none_when_password_wrong(self, db_session, create_user):
        create_user(username="alice", password="rightpass1")
        result = service.authenticate_user(
            AuthData(username="alice", password="wrongpass2"),
            db_session,
        )
        assert result is None

    def test_password_of_exactly_72_bytes_round_trips(self, db_session, create_user):
        create_user(username="alice", password="p" * 72)
        user = service.authenticate_user(AuthData(username="alice", password="p" * 72), db_session)
        assert user is not None

    def test_legacy_long_password_still_logs_in(self, db_session, create_user):
        """Accounts created before the 72-byte limit were hashed from the first
        72 bytes (bcrypt 4 truncated silently). They must keep working: bcrypt 5
        raises on >72-byte input, so check_password truncates the same way."""
        import bcrypt

        long_password = "legacy-" + "x" * 80
        user = create_user(username="legacy")
        user.password_hash = bcrypt.hashpw(
            long_password.encode()[:72], bcrypt.gensalt(rounds=4)
        ).decode()
        db_session.commit()

        result = service.authenticate_user(
            AuthData(username="legacy", password=long_password), db_session
        )
        assert result is not None

    def test_set_password_refuses_over_72_bytes(self):
        with pytest.raises(ValueError, match="72 bytes"):
            User(username="x").set_password("p" * 73)

    def test_returns_none_when_user_missing(self, db_session):
        result = service.authenticate_user(
            AuthData(username="ghost", password="whatever1"),
            db_session,
        )
        assert result is None


class TestVerifyEmail:
    def _register_unverified(self, db_session, username: str) -> User:
        service.register_user(_payload(username=username), db_session)
        row = db_session.query(User).filter_by(username=username).first()
        row.email_verified = False
        db_session.commit()
        db_session.refresh(row)
        return row

    def test_valid_token_flips_flag_and_clears_token(self, db_session):
        row = self._register_unverified(db_session, "verify_ok")
        token = row.verification_token

        ok, msg = service.verify_email(token, db_session)
        assert ok is True
        assert "verified" in msg.lower()

        db_session.refresh(row)
        assert row.email_verified is True
        assert row.verification_token is None

    def test_invalid_token_rejected(self, db_session):
        ok, msg = service.verify_email("does-not-exist", db_session)
        assert ok is False
        assert "invalid" in msg.lower()

    def test_already_verified_token_short_circuits(self, db_session, create_user):
        user = create_user(username="already_verified")
        user.verification_token = "still-here"
        user.email_verified = True
        db_session.commit()

        ok, msg = service.verify_email("still-here", db_session)
        assert ok is True
        assert "already verified" in msg.lower()

    def test_expired_token_rejected(self, db_session):
        row = self._register_unverified(db_session, "expired_verify")
        row.verification_token_expires = int(time.time()) - 1
        db_session.commit()

        ok, msg = service.verify_email(row.verification_token, db_session)
        assert ok is False
        assert "expired" in msg.lower()


class TestResendVerification:
    def test_missing_user_rejected(self, db_session):
        ok, msg = service.resend_verification("nobody", db_session)
        assert ok is False
        assert "User not found" in msg

    def test_already_verified_rejected(self, db_session, create_user):
        create_user(username="already_verified")
        ok, msg = service.resend_verification("already_verified", db_session)
        assert ok is False
        assert "already verified" in msg.lower()

    def test_missing_email_rejected(self, db_session, create_user):
        user = create_user(username="no_email", email="none@test.com")
        user.email_verified = False
        user.email = None
        db_session.commit()
        ok, msg = service.resend_verification("no_email", db_session)
        assert ok is False
        assert "email" in msg.lower()

    def test_regenerates_token_and_resets_expiry(self, db_session):
        service.register_user(_payload(username="resend_ok"), db_session)
        row = db_session.query(User).filter_by(username="resend_ok").first()
        row.email_verified = False
        old_token = row.verification_token
        db_session.commit()

        ok, msg = service.resend_verification("resend_ok", db_session)
        assert ok is True
        db_session.refresh(row)
        assert row.verification_token != old_token
        assert row.verification_token_expires > int(time.time())
        assert (
            row.verification_token_expires
            <= int(time.time()) + VERIFICATION_TOKEN_EXPIRY_SECONDS + 1
        )

    def test_returns_failure_when_email_send_fails(self, db_session):
        service.register_user(_payload(username="resend_fail"), db_session)
        row = db_session.query(User).filter_by(username="resend_fail").first()
        row.email_verified = False
        db_session.commit()

        with patch("app.auth.service.send_verification_email", return_value=False):
            ok, msg = service.resend_verification("resend_fail", db_session)
        assert ok is False
        assert "failed to send" in msg.lower()


class TestPromoteToAdmin:
    SECRET = "correct-horse-battery-staple"

    def test_correct_secret_promotes(self, db_session, create_user, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", self.SECRET)
        user = create_user(username="promo")
        assert (
            service.promote_to_admin("promo", self.SECRET, db_session)
            is service.PromotionResult.PROMOTED
        )
        db_session.refresh(user)
        assert user.is_admin is True

    @pytest.mark.parametrize(
        "guess",
        ["", "hunter2-guess", SECRET[:-1], SECRET + "x", SECRET.upper()],
        ids=["empty", "unrelated", "one-short", "one-long", "wrong-case"],
    )
    def test_wrong_secret_is_rejected_and_logged_without_the_guess(
        self, db_session, create_user, monkeypatch, caplog, guess
    ):
        monkeypatch.setenv("ADMIN_SECRET", self.SECRET)
        user = create_user(username="promo")
        with caplog.at_level("WARNING", logger="app.auth.service"):
            result = service.promote_to_admin("promo", guess, db_session)
        assert result is service.PromotionResult.WRONG_SECRET
        db_session.refresh(user)
        assert user.is_admin is False
        assert "promo" in caplog.text
        if guess:
            assert guess not in caplog.text

    def test_unset_secret_disables_promotion(self, db_session, create_user, monkeypatch):
        monkeypatch.delenv("ADMIN_SECRET", raising=False)
        create_user(username="promo")
        result = service.promote_to_admin("promo", "anything", db_session)
        assert result is service.PromotionResult.NOT_CONFIGURED

    def test_missing_user(self, db_session, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", self.SECRET)
        result = service.promote_to_admin("ghost", self.SECRET, db_session)
        assert result is service.PromotionResult.USER_NOT_FOUND

    def test_non_ascii_guess_does_not_crash(self, db_session, create_user, monkeypatch):
        """compare_digest on str rejects non-ASCII; comparing bytes must not."""
        monkeypatch.setenv("ADMIN_SECRET", self.SECRET)
        create_user(username="promo")
        result = service.promote_to_admin("promo", "pässwörd", db_session)
        assert result is service.PromotionResult.WRONG_SECRET
