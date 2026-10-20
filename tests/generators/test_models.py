"""Tests for app/generators/models.py — SQLAlchemy ORM relationships and constraints."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.generators.models import GeneratorProfile, GeneratorRun, GeneratorSource


class TestGeneratorSource:
    def test_defaults_populated_on_insert(self, db_session):
        source = GeneratorSource(name="S", site_url="https://example.com", config={})
        db_session.add(source)
        db_session.commit()

        assert source.is_active is True
        assert source.total_posts_created == 0
        assert source.consecutive_failures == 0
        assert source.run_interval_minutes == 0

    def test_cascade_deletes_profiles_and_runs(self, db_session, create_user):
        source = GeneratorSource(name="S", site_url="https://example.com", config={})
        db_session.add(source)
        db_session.commit()

        bot = create_user(username="bot1")
        db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
        db_session.add(GeneratorRun(source_id=source.id, started_at=1, status="running"))
        db_session.commit()

        db_session.delete(source)
        db_session.commit()

        assert db_session.query(GeneratorProfile).count() == 0
        assert db_session.query(GeneratorRun).count() == 0


class TestGeneratorProfile:
    def test_duplicate_source_user_pair_rejected(self, db_session, create_user):
        source = GeneratorSource(name="S", site_url="https://x.com", config={})
        db_session.add(source)
        db_session.commit()

        bot = create_user(username="bot2")
        db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
        db_session.commit()

        db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestGeneratorRun:
    def test_run_defaults(self, db_session):
        source = GeneratorSource(name="S", site_url="https://x.com", config={})
        db_session.add(source)
        db_session.commit()

        run = GeneratorRun(source_id=source.id, started_at=1, status="running")
        db_session.add(run)
        db_session.commit()

        assert run.items_found == 0
        assert run.items_posted == 0
        assert run.selectors_updated is False
