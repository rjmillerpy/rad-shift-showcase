"""The API survives its database going away and coming back.

Managed Postgres drops connections: RDS restarts and failovers, Neon's free
plan suspending when idle. The connection pool must not hand out a dead
connection afterwards (app/common/db.py: pool_pre_ping). Before that fix the
first request after a restart failed with "server closed the connection".
"""

import httpx

from e2e.helpers import restart_database_and_wait


def test_first_request_after_a_database_restart_succeeds(api: httpx.Client) -> None:
    assert api.get("/health").status_code == 200  # the pool now holds a live connection

    restart_database_and_wait()

    # No retries: the very first request must succeed.
    response = api.get("/health")
    assert response.status_code == 200, response.text
    assert response.json()["checks"]["database"] == "ok"
