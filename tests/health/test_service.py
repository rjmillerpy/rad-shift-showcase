"""Tests for app/health/service.py."""

from app.health import service
from app.health.schema import HealthStatus


class TestLiveness:
    def test_ok(self):
        assert service.liveness().status is HealthStatus.OK


class TestReadiness:
    def test_ok_when_database_answers(self, db_session):
        result = service.readiness(db_session)
        assert result.status is HealthStatus.OK
        assert result.checks.database is HealthStatus.OK

    def test_unavailable_when_database_is_unreachable(self, unreachable_db):
        result = service.readiness(unreachable_db)
        assert result.status is HealthStatus.UNAVAILABLE
        assert result.checks.database is HealthStatus.UNAVAILABLE

    def test_failure_is_logged_with_the_cause(self, unreachable_db, caplog):
        with caplog.at_level("ERROR", logger="app.health.service"):
            service.readiness(unreachable_db)
        assert "database ping failed" in caplog.text
        assert "unable to open database file" in caplog.text
