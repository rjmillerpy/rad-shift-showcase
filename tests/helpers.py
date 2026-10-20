"""Shared HTTP-level test helpers used by API contract tests.

These do NOT replace the DB-level fixtures in conftest (create_user/auth_header).
Use these when the test specifically verifies the signup/login HTTP contract.
"""

from pathlib import Path

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.contrib.provider.flagd.config import ResolverType


def signup(client, username: str = "apiuser", password: str = "password123"):
    """Sign up a user via POST /auth/signup, return the Response."""
    return client.post(
        "/auth/signup",
        json={"username": username, "password": password, "email": f"{username}@test.com"},
    )


def login(client, username: str = "apiuser", password: str = "password123") -> dict:
    """Log in and return an Authorization header dict suitable for subsequent requests."""
    res = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def setup_user(client, username: str = "apiuser") -> dict:
    """Convenience: signup + login, return auth headers."""
    signup(client, username)
    return login(client, username)


def make_post(client, headers: dict, text: str = "Test post", **form_fields):
    """Create a post via POST /posts/add multipart form."""
    data = {"text": text, "post_metadata": "{}", "is_draft": "false", **form_fields}
    return client.post("/posts/add", data=data, headers=headers)


# ── Feature flags ───────────────────────────────────────────────────────────

FLAGS_FILE = Path(__file__).resolve().parent.parent / "flags" / "flags.flagd.json"


def serve_flags_file(path: Path) -> None:
    """Evaluate flags from `path` with the app's flagd provider, in its FILE mode."""
    api.set_provider_and_wait(
        FlagdProvider(resolver_type=ResolverType.FILE, offline_flag_source_path=str(path))
    )
