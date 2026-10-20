"""Tests for app/common/email.py — Resend + console fallback."""

from unittest.mock import MagicMock, patch

import httpx
import pytest


class TestExpiryPhrase:
    def test_derives_from_auth_constants(self):
        """The '24 hours' phrase must trace back to the auth constants (rule 16)."""
        from app.auth.constants import VERIFICATION_TOKEN_EXPIRY_SECONDS
        from app.common.email import _expiry_phrase

        expected_hours = VERIFICATION_TOKEN_EXPIRY_SECONDS // 3600
        assert f"{expected_hours} hours" in _expiry_phrase()


class TestSendVerificationEmail:
    def test_console_mode_returns_true_without_api_key(self, monkeypatch):
        monkeypatch.setattr("app.common.email.RESEND_API_KEY", None)
        from app.common.email import send_verification_email

        assert send_verification_email("user@example.com", "abc123") is True

    def test_resend_success(self, monkeypatch):
        monkeypatch.setattr("app.common.email.RESEND_API_KEY", "re_test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("httpx.post", return_value=mock_response) as mock_post:
            from app.common.email import send_verification_email

            assert send_verification_email("user@example.com", "token123") is True
            mock_post.assert_called_once()

    def test_resend_uses_configured_timeout(self, monkeypatch):
        monkeypatch.setattr("app.common.email.RESEND_API_KEY", "re_test_key")
        from app.common.constants import EMAIL_TIMEOUT_SECONDS

        mock_response = MagicMock(status_code=200)
        with patch("httpx.post", return_value=mock_response) as mock_post:
            from app.common.email import send_verification_email

            send_verification_email("user@example.com", "token123")
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["timeout"] == EMAIL_TIMEOUT_SECONDS

    def test_resend_api_error_returns_false(self, monkeypatch):
        monkeypatch.setattr("app.common.email.RESEND_API_KEY", "re_test_key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        with patch("httpx.post", return_value=mock_response):
            from app.common.email import send_verification_email

            assert send_verification_email("user@example.com", "token123") is False

    def test_resend_timeout_returns_false(self, monkeypatch):
        monkeypatch.setattr("app.common.email.RESEND_API_KEY", "re_test_key")
        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            from app.common.email import send_verification_email

            assert send_verification_email("user@example.com", "token123") is False

    def test_resend_generic_exception_returns_false(self, monkeypatch):
        monkeypatch.setattr("app.common.email.RESEND_API_KEY", "re_test_key")
        with patch("httpx.post", side_effect=ConnectionError("network down")):
            from app.common.email import send_verification_email

            assert send_verification_email("user@example.com", "token123") is False

    @pytest.mark.parametrize(
        "to_email,token",
        [
            ("alice@example.com", "tok1"),
            ("bob@test.org", "tok2"),
            ("x@y.z", "short"),
        ],
        ids=["alice", "bob", "single_char_local"],
    )
    def test_console_mode_various_inputs(self, monkeypatch, to_email, token):
        monkeypatch.setattr("app.common.email.RESEND_API_KEY", None)
        from app.common.email import send_verification_email

        assert send_verification_email(to_email, token) is True
