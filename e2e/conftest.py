"""Fixtures for the end-to-end suite.

These tests run against the live stack started by e2e/run.sh: a real browser
talks to Next.js on :3000, which (from the browser) calls the API on :5000,
which writes to Postgres (published on :5433). Nothing is mocked.
"""

import uuid

import httpx
import pytest

from e2e.helpers import API_URL, TLS_CA, tls_verify, verification_token_for


@pytest.fixture
def new_user() -> dict:
    """Credentials for a user that doesn't exist yet (unique per test)."""
    suffix = uuid.uuid4().hex[:10]
    return {
        "username": f"e2e_{suffix}",
        "email": f"e2e_{suffix}@example.com",
        "password": f"pw-{uuid.uuid4().hex}",
    }


@pytest.fixture
def api() -> httpx.Client:
    # In TLS mode, verify against Caddy's local CA, never skip verification.
    with httpx.Client(base_url=API_URL, timeout=15, verify=tls_verify()) as client:
        yield client


@pytest.fixture
def verified_user(api: httpx.Client, new_user: dict) -> dict:
    """A signed-up, email-verified user created through the API (not the UI).

    For tests whose subject is something other than signup itself.
    """
    api.post("/auth/signup", json=new_user).raise_for_status()
    token = verification_token_for(new_user["username"])
    api.get("/auth/verify", params={"token": token}).raise_for_status()
    login = api.post(
        "/auth/login",
        json={"username": new_user["username"], "password": new_user["password"]},
    )
    login.raise_for_status()
    return {**new_user, "access_token": login.json()["access_token"]}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """In TLS mode the browser accepts Caddy's local certificates.

    Chromium only trusts roots from an NSS database, so the browser skips the
    check instead; the API tests verify the certificate properly.
    """
    return {**browser_context_args, "ignore_https_errors": bool(TLS_CA)}
