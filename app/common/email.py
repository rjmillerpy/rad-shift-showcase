"""Email delivery: Resend when RESEND_API_KEY is set, console for development."""

import logging
import os

import httpx

from app.auth.constants import VERIFICATION_TOKEN_EXPIRY_SECONDS
from app.common.constants import DEFAULT_FROM_EMAIL, EMAIL_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", DEFAULT_FROM_EMAIL)
APP_URL = os.getenv("APP_URL", "http://localhost:3000")


def _expiry_phrase() -> str:
    hours = VERIFICATION_TOKEN_EXPIRY_SECONDS // 3600
    return f"This link expires in {hours} hours."


def send_verification_email(to_email: str, token: str) -> bool:
    """Send a verification email. Returns True on success (or console fallback)."""
    verify_url = f"{APP_URL}/verify?token={token}"
    if RESEND_API_KEY:
        return _send_via_resend(to_email, verify_url)
    return _send_via_console(to_email, verify_url)


def _resend_html(verify_url: str) -> str:
    return (
        "<h2>Welcome to rad-shift!</h2>"
        "<p>Click the link below to verify your email address:</p>"
        f'<p><a href="{verify_url}">{verify_url}</a></p>'
        f"<p>{_expiry_phrase()}</p>"
    )


def _send_via_resend(to_email: str, verify_url: str) -> bool:
    """Call the Resend API. Broad `Exception` catch is intentional: email is
    best-effort — any transport/API failure degrades to False and is logged."""
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": "Verify your rad-shift account",
                "html": _resend_html(verify_url),
            },
            timeout=EMAIL_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — see docstring above
        logger.error("Failed to send email via Resend: %s", exc)
        return False

    if response.status_code == 200:
        logger.info("Verification email sent to %s via Resend", to_email)
        return True
    logger.error("Resend API error: %s %s", response.status_code, response.text)
    return False


def _send_via_console(to_email: str, verify_url: str) -> bool:
    logger.info("=" * 60)
    logger.info("VERIFICATION EMAIL (console mode)")
    logger.info("To: %s", to_email)
    logger.info("Verify URL: %s", verify_url)
    logger.info("=" * 60)
    return True
