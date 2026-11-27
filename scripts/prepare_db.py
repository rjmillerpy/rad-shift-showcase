"""Bring the database schema up to date before the API starts.

Run by docker-entrypoint.sh on every container start:

    python scripts/prepare_db.py

* Fresh database (no tables): create every table from the SQLAlchemy models
  and stamp Alembic at head. Several tables (widgets, blog, amble cursors)
  have no migration at all, so replaying the history would not produce the
  full schema anyway.
* Database already managed by Alembic: `alembic upgrade head`.
* Tables exist but Alembic has never run (created by `create_all` alone):
  fill in any missing tables and stamp head, with a warning.

Several copies can start at once (Kubernetes rolls out API replicas in
parallel, deploy/helm/), so the work runs under a PostgreSQL advisory lock:
the first one migrates, the others wait and then find nothing to do. Two
create_all() calls racing on an empty database would otherwise collide on
CREATE TABLE.
"""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from sqlalchemy import Connection, inspect, text  # noqa: E402

# Import every models module so all tables are registered on Base.metadata.
import app.admin.models  # noqa: E402,F401
import app.amble.avatar.models  # noqa: E402,F401
import app.amble.content.models  # noqa: E402,F401
import app.auth.models  # noqa: E402,F401
import app.blog.models  # noqa: E402,F401
import app.community_notes.models  # noqa: E402,F401
import app.engagement.models  # noqa: E402,F401
import app.generators.models  # noqa: E402,F401
import app.posts.models  # noqa: E402,F401
import app.ratelimit.models  # noqa: E402,F401
import app.web_analytics.models  # noqa: E402,F401
import app.widgets.models  # noqa: E402,F401
from app.common.db import Base, engine  # noqa: E402


def log(message: str) -> None:
    # print, not logging: alembic/env.py calls logging.config.fileConfig(),
    # which disables loggers created before it runs (including ours).
    print(f"[prepare_db] {message}", flush=True)


ALEMBIC_VERSION_TABLE = "alembic_version"
# Any fixed 64-bit number; every copy of this script must use the same one.
MIGRATION_LOCK_ID = 7_265_646_165_746


@contextmanager
def migration_lock(connection: Connection) -> Iterator[None]:
    """Hold a session-level advisory lock on PostgreSQL; nothing elsewhere.

    Session-level, not transaction-level: Alembic commits as it goes, and
    the lock must outlive those commits. Released when the block ends, or
    by PostgreSQL itself if this process dies holding it.
    """
    if connection.dialect.name != "postgresql":
        yield
        return
    connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
    try:
        yield
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})


def main() -> None:
    with engine.connect() as connection, migration_lock(connection):
        prepare()


def prepare() -> None:
    alembic_cfg = AlembicConfig(os.path.join(ROOT, "alembic.ini"))
    tables = set(inspect(engine).get_table_names())

    if ALEMBIC_VERSION_TABLE in tables:
        log("Existing Alembic-managed database: upgrading to head")
        command.upgrade(alembic_cfg, "head")
        log("Schema up to date")
        return

    if tables:
        log(
            f"WARNING: found {len(tables)} tables but no {ALEMBIC_VERSION_TABLE} "
            "table; creating any missing tables and stamping head. Check the "
            "schema by hand if this database predates the current models."
        )
    else:
        log("Empty database: creating schema from models")

    Base.metadata.create_all(bind=engine)
    command.stamp(alembic_cfg, "head")
    log("Schema ready; Alembic stamped at head")


if __name__ == "__main__":
    main()
