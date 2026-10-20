"""Tests for app/generators/scheduler.py — background scheduling logic."""

import threading
import time
from unittest.mock import MagicMock, patch

from app.generators import scheduler as scheduler_mod
from app.generators.models import GeneratorSource
from app.generators.scheduler import (
    _find_due_sources,
    _run_due_source,
    _scheduler_loop,
    start_scheduler,
    stop_scheduler,
)


class TestFindDueSources:
    """Tests for _find_due_sources query logic."""

    def test_returns_due_source(self, db_session):
        now = int(time.time())
        source = GeneratorSource(
            name="Due Source",
            site_url="https://example.com",
            is_active=True,
            run_interval_minutes=10,
            last_run_at=now - 700,  # 700s ago, interval is 600s
            selectors={"post_container": "div", "text": "p"},
        )
        db_session.add(source)
        db_session.commit()

        due = _find_due_sources(db_session)
        assert len(due) == 1
        assert due[0].id == source.id

    def test_skips_not_yet_due(self, db_session):
        now = int(time.time())
        source = GeneratorSource(
            name="Not Due",
            site_url="https://example.com",
            is_active=True,
            run_interval_minutes=60,
            last_run_at=now - 30,  # 30s ago, interval is 3600s
            selectors={"post_container": "div", "text": "p"},
        )
        db_session.add(source)
        db_session.commit()

        due = _find_due_sources(db_session)
        assert len(due) == 0

    def test_skips_inactive_source(self, db_session):
        source = GeneratorSource(
            name="Inactive",
            site_url="https://example.com",
            is_active=False,
            run_interval_minutes=10,
            last_run_at=0,
            selectors={"post_container": "div", "text": "p"},
        )
        db_session.add(source)
        db_session.commit()

        due = _find_due_sources(db_session)
        assert len(due) == 0

    def test_skips_manual_only(self, db_session):
        source = GeneratorSource(
            name="Manual",
            site_url="https://example.com",
            is_active=True,
            run_interval_minutes=0,
            selectors={"post_container": "div", "text": "p"},
        )
        db_session.add(source)
        db_session.commit()

        due = _find_due_sources(db_session)
        assert len(due) == 0

    def test_skips_source_without_selectors(self, db_session):
        source = GeneratorSource(
            name="No Selectors",
            site_url="https://example.com",
            is_active=True,
            run_interval_minutes=10,
            last_run_at=0,
            selectors=None,
        )
        db_session.add(source)
        db_session.commit()

        due = _find_due_sources(db_session)
        assert len(due) == 0

    def test_never_run_source_is_due(self, db_session):
        """Source with last_run_at=None should be considered due."""
        source = GeneratorSource(
            name="Never Run",
            site_url="https://example.com",
            is_active=True,
            run_interval_minutes=10,
            last_run_at=None,
            selectors={"post_container": "div", "text": "p"},
        )
        db_session.add(source)
        db_session.commit()

        due = _find_due_sources(db_session)
        assert len(due) == 1


class TestSchedulerLifecycle:
    """Tests for start/stop scheduler.

    These tests patch the module-level ``_scheduler_loop`` to stop the thread
    from actually polling/sleeping during unit tests. The true external
    boundaries (``SessionLocal``, ``time.sleep``) live deeper inside the loop;
    substituting the whole loop is the narrowest isolation that still exercises
    the lifecycle contract (start creates a live thread, stop joins it).
    """

    def test_start_and_stop(self):
        """Scheduler thread starts and stops cleanly."""
        # Intentionally mocks internal helper _scheduler_loop — the true boundary
        # is time.sleep inside the loop, but we need to prevent the loop from
        # blocking the test on a real 60s poll interval.
        with patch("app.generators.scheduler._scheduler_loop") as mock_loop:
            mock_loop.side_effect = lambda stop_event: stop_event.wait()
            start_scheduler()
            # Give thread a moment to start
            import app.generators.scheduler as mod

            assert mod._thread is not None
            assert mod._thread.is_alive()

            stop_scheduler()
            assert mod._thread is None

    def test_start_is_idempotent(self):
        """Calling start twice doesn't create two threads."""
        # Intentionally mocks internal helper _scheduler_loop — same reason as above.
        with patch("app.generators.scheduler._scheduler_loop") as mock_loop:
            mock_loop.side_effect = lambda stop_event: stop_event.wait()
            start_scheduler()

            import app.generators.scheduler as mod

            first_thread = mod._thread

            start_scheduler()
            assert mod._thread is first_thread

            stop_scheduler()

    def test_stop_without_start_is_a_noop(self):
        """stop_scheduler must be safe to call even if start was never called."""
        scheduler_mod._stop_event = None
        scheduler_mod._thread = None
        stop_scheduler()  # should not raise
        assert scheduler_mod._thread is None


class TestRunDueSource:
    """Tests for _run_due_source — invokes the scraper in an isolated session."""

    def test_success_path_logs_result(self, caplog):
        run_obj = MagicMock(items_found=3, items_posted=2)
        with (
            patch("app.generators.scheduler.run_scraper", return_value=run_obj) as mock_run,
            patch("app.generators.scheduler.SessionLocal") as mock_session_cls,
        ):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            with caplog.at_level("INFO"):
                _run_due_source(42)
        mock_run.assert_called_once_with(42, mock_db)
        mock_db.close.assert_called_once()
        assert any("found=3 posted=2" in rec.getMessage() for rec in caplog.records)

    def test_scraper_exception_is_isolated_and_logged(self, caplog):
        with (
            patch("app.generators.scheduler.run_scraper", side_effect=RuntimeError("boom")),
            patch("app.generators.scheduler.SessionLocal") as mock_session_cls,
        ):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            _run_due_source(42)  # must not raise — error isolation contract
        mock_db.close.assert_called_once()
        assert any(
            "Scheduled run failed for source 42" in rec.getMessage() for rec in caplog.records
        )


class TestSchedulerLoop:
    """Tests for _scheduler_loop — polls and dispatches due sources.

    These tests patch the peer helpers _find_due_sources / _run_due_source so
    the loop's orchestration logic (exit conditions, exception-isolation,
    dispatch) is testable without spinning up a full DB + scraper + Anthropic
    stack. The standalone behavior of those helpers is covered above in
    TestFindDueSources / TestRunDueSource with minimal mocking.
    """

    def test_loop_exits_when_stop_event_set(self):
        stop = threading.Event()
        stop.set()
        with patch("app.generators.scheduler.SessionLocal"):
            _scheduler_loop(stop)  # returns without raising

    def test_loop_dispatches_due_source_then_stops(self):
        due = MagicMock(id=7, name="Due")
        stop = threading.Event()

        def run_and_stop(source_id: int) -> None:
            stop.set()

        # Intentionally mocks internal helpers _find_due_sources and
        # _run_due_source — the true boundaries (SessionLocal and run_scraper)
        # are reached through a call chain that would require mocking the whole
        # scraper + analyzer + httpx stack to exercise this one-line dispatch.
        with (
            patch.object(stop, "wait", return_value=True),
            patch("app.generators.scheduler.SessionLocal") as mock_session_cls,
            patch("app.generators.scheduler._find_due_sources", return_value=[due]),
            patch("app.generators.scheduler._run_due_source", side_effect=run_and_stop) as mock_run,
        ):
            mock_session_cls.return_value = MagicMock()
            _scheduler_loop(stop)
        mock_run.assert_called_once_with(7)

    def test_query_exception_is_logged_and_loop_continues(self, caplog):
        stop = threading.Event()
        call_count = {"n": 0}

        def wait_side_effect(_seconds: float) -> bool:
            call_count["n"] += 1
            if call_count["n"] >= 2:
                stop.set()
            return True

        # Intentionally mocks _find_due_sources to inject a failure —
        # simulating "DB down" via the true SessionLocal boundary would require
        # a brittle setup; error-isolation is the contract under test.
        with (
            patch.object(stop, "wait", side_effect=wait_side_effect),
            patch("app.generators.scheduler.SessionLocal") as mock_session_cls,
            patch(
                "app.generators.scheduler._find_due_sources", side_effect=RuntimeError("db down")
            ),
        ):
            mock_session_cls.return_value = MagicMock()
            with caplog.at_level("ERROR"):
                _scheduler_loop(stop)
        assert any("Scheduler failed to query" in rec.getMessage() for rec in caplog.records)
