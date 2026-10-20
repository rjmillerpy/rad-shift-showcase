"""Tests for app.common.db module."""

import contextlib


class TestBase:
    def test_base_is_importable(self):
        from app.common.db import Base

        # SQLAlchemy 1.x declarative_base returns a class whose metaclass
        # handles registry; just confirm it has metadata.
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "__tablename__") or hasattr(Base, "metadata")

    def test_base_has_metadata_tables(self):
        from app.common.db import Base

        # After models are imported, tables should be registered
        assert len(Base.metadata.tables) > 0


class TestGetDb:
    def test_yields_session_and_closes(self):
        from app.common.db import get_db

        gen = get_db()
        session = next(gen)
        assert session is not None
        # Cleanup: drive generator to completion
        with contextlib.suppress(StopIteration):
            next(gen)

    def test_get_db_is_generator(self):
        import types

        from app.common.db import get_db

        assert isinstance(get_db(), types.GeneratorType)


class TestCreateTables:
    def test_create_tables_callable(self):
        from app.common.db import create_tables

        # In tests, create_tables is monkey-patched to a no-op lambda.
        # Just verify it's callable and doesn't raise.
        create_tables()


class TestGetDbRollback:
    def test_exception_in_body_triggers_rollback(self):
        """Throwing into the generator hits the except branch that rolls back."""
        from unittest.mock import MagicMock, patch

        from app.common import db as db_mod

        fake_session = MagicMock()
        fake_factory = MagicMock(return_value=fake_session)
        with patch.object(db_mod, "SessionLocal", fake_factory):
            gen = db_mod.get_db()
            next(gen)  # start the generator, hits `yield db`
            with contextlib.suppress(RuntimeError):
                gen.throw(RuntimeError("boom"))
        fake_session.rollback.assert_called_once()
        fake_session.close.assert_called_once()


class TestBuildEngine:
    """Connection settings for managed Postgres (rule 67); the end-to-end
    behaviour is covered by e2e/test_resilience.py."""

    UNREACHABLE = "postgresql+psycopg2://user:pw@192.0.2.1:5432/db"  # TEST-NET-1: never routed

    def test_unreachable_database_fails_within_the_connect_timeout(self):
        import time

        import pytest
        from sqlalchemy.exc import OperationalError

        from app.common.db import build_engine

        engine = build_engine(self.UNREACHABLE, connect_timeout=1)
        start = time.monotonic()
        with pytest.raises(OperationalError):
            engine.connect()
        assert time.monotonic() - start < 5

    def test_pool_checks_and_recycles_connections(self):
        from app.common.constants import DB_POOL_RECYCLE_SECONDS
        from app.common.db import build_engine

        engine = build_engine(self.UNREACHABLE)
        # Configuration contract: SQLAlchemy exposes no public getter for these.
        assert engine.pool._pre_ping is True
        assert engine.pool._recycle == DB_POOL_RECYCLE_SECONDS
