"""Plain helpers for the e2e suite (fixtures live in conftest.py)."""

import os
import ssl
import subprocess
import time
from pathlib import Path

import psycopg2

API_URL = os.getenv("E2E_API_URL", "http://localhost:5000")
DB_DSN = os.getenv(
    "E2E_DB_DSN",
    "postgresql://radshift:radshift-local@localhost:5433/radshift",
)


REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PROJECT = os.getenv("E2E_COMPOSE_PROJECT", "radshift-e2e")
# Colon-separated, as run.sh builds it (compose.tls.yaml is added in TLS mode).
COMPOSE_FILES = os.getenv("E2E_COMPOSE_FILES", "compose.yaml:e2e/compose.e2e.yaml").split(":")
# Path to the local CA's root certificate; set by run.sh only in TLS mode.
TLS_CA = os.getenv("E2E_TLS_CA", "")
# Set by run.sh when compose.observability.yaml is part of the stack (E2E_OBS=1).
OBSERVABILITY = os.getenv("E2E_OBS", "0") == "1"


def tls_verify() -> ssl.SSLContext | bool:
    """What httpx should verify server certificates against: Caddy's local CA in TLS mode, else the defaults."""
    return ssl.create_default_context(cafile=TLS_CA) if TLS_CA else True


DB_READY_TIMEOUT_SECONDS = 30


def compose(*args: str) -> subprocess.CompletedProcess:
    """Run a docker compose command against the e2e stack (same files as run.sh)."""
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            COMPOSE_PROJECT,
            *(arg for path in COMPOSE_FILES for arg in ("-f", path)),
            *args,
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def restart_database_and_wait() -> None:
    """Restart Postgres (dropping every server-side connection), then wait until it accepts connections."""
    compose("restart", "db")
    deadline = time.monotonic() + DB_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            psycopg2.connect(DB_DSN, connect_timeout=2).close()
            return
        except psycopg2.OperationalError:
            time.sleep(0.5)
    raise TimeoutError(f"database not ready {DB_READY_TIMEOUT_SECONDS}s after restart")


def verification_token_for(username: str) -> str:
    """Read the emailed verification token straight from the database.

    Stands in for "open the email and click the link": in the test stack the
    email is only logged, but the token it would contain is in users.
    """
    conn = psycopg2.connect(DB_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT verification_token FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row and row[0], f"no pending verification token for {username}"
    return row[0]
