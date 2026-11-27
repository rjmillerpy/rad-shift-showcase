"""scripts/prepare_db.py: the migration lock.

What the lock is for (pods started together migrate one at a time) needs
PostgreSQL: the Kubernetes drill starts API pods together on an empty
database (deploy/README.md). Off PostgreSQL it must stay out of the way.
"""

import pytest
from sqlalchemy import text

from scripts.prepare_db import migration_lock
from tests.conftest import test_engine


def test_the_lock_is_a_no_op_off_postgresql():
    with test_engine.connect() as connection, migration_lock(connection):
        assert connection.execute(text("SELECT 1")).scalar() == 1


def test_an_error_inside_still_reaches_the_caller():
    with (
        test_engine.connect() as connection,
        pytest.raises(RuntimeError, match="migration failed"),
        migration_lock(connection),
    ):
        raise RuntimeError("migration failed")


def test_every_module_that_defines_tables_is_imported():
    """On a fresh database prepare_db creates tables from what it has imported,
    then stamps Alembic at head: a module missing from its imports means its
    tables never exist, and no later migration will add them (community notes
    were missing for a day)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    script = (root / "scripts" / "prepare_db.py").read_text()
    with_tables = {
        ".".join(path.relative_to(root).with_suffix("").parts)
        for path in (root / "app").rglob("models.py")
        if "__tablename__" in path.read_text()
    }
    missing = {module for module in with_tables if f"import {module}  " not in script}
    assert with_tables and not missing, f"prepare_db.py doesn't import {sorted(missing)}"
