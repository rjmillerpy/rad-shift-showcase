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
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

# Import every models module so all tables are registered on Base.metadata.
import app.admin.models  # noqa: E402,F401
import app.amble.avatar.models  # noqa: E402,F401
import app.amble.content.models  # noqa: E402,F401
import app.auth.models  # noqa: E402,F401
import app.blog.models  # noqa: E402,F401
import app.generators.models  # noqa: E402,F401
import app.posts.models  # noqa: E402,F401
import app.widgets.models  # noqa: E402,F401
from app.common.db import Base, engine  # noqa: E402


def log(message: str) -> None:
    # print, not logging: alembic/env.py calls logging.config.fileConfig(),
    # which disables loggers created before it runs (including ours).
    print(f"[prepare_db] {message}", flush=True)


ALEMBIC_VERSION_TABLE = "alembic_version"


def main() -> None:
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
