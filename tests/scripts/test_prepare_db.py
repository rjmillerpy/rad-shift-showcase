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
