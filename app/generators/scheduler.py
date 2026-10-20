"""Background scheduler that runs due generator sources on their configured interval.

Starts a daemon thread on app startup. Checks every SCHEDULER_POLL_INTERVAL_SECONDS for sources
where `is_active=True`, `run_interval_minutes > 0`, and enough time has elapsed since
last_run_at. Runs each due source in sequence with error isolation.
"""

import logging
import threading
import time

from sqlalchemy.orm import Session

from app.common.db import SessionLocal
from app.generators.constants import (
    SCHEDULER_JOIN_TIMEOUT_SECONDS,
    SCHEDULER_MAX_SOURCES_PER_TICK,
    SCHEDULER_POLL_INTERVAL_SECONDS,
)
from app.generators.models import GeneratorSource
from app.generators.service import run_scraper

logger = logging.getLogger(__name__)


def _find_due_sources(db: Session) -> list[GeneratorSource]:
    """Return active sources whose interval has elapsed since last run."""
    now = int(time.time())
    active_sources = (
        db.query(GeneratorSource)
        .filter(
            GeneratorSource.is_active == True,  # noqa: E712 — SQLAlchemy column expression
            GeneratorSource.run_interval_minutes > 0,
        )
        .all()
    )

    due: list[GeneratorSource] = []
    for source in active_sources:
        if not source.selectors:
            continue
        interval_seconds = source.run_interval_minutes * 60
        last_run = source.last_run_at or 0
        is_due = (now - last_run) >= interval_seconds
        if is_due:
            due.append(source)

    return due[:SCHEDULER_MAX_SOURCES_PER_TICK]


def _run_due_source(source_id: int) -> None:
    """Run a single source in its own DB session for error isolation."""
    db = SessionLocal()
    try:
        run = run_scraper(source_id, db)
        logger.info(
            "Scheduled run for source %d: found=%d posted=%d",
            source_id,
            run.items_found,
            run.items_posted,
        )
    except Exception as exc:  # noqa: BLE001
        # Background scheduler must absorb *any* per-source failure so a single
        # bad source can't kill the poll loop. Logged with source id for triage.
        logger.error("Scheduled run failed for source %d: %s", source_id, exc)
    finally:
        db.close()


def _scheduler_loop(stop_event: threading.Event) -> None:
    """Main loop — polls for due sources and runs them."""
    logger.info("Generator scheduler started (poll every %ds)", SCHEDULER_POLL_INTERVAL_SECONDS)

    while not stop_event.is_set():
        stop_event.wait(SCHEDULER_POLL_INTERVAL_SECONDS)
        if stop_event.is_set():
            break

        db = SessionLocal()
        try:
            due_sources = _find_due_sources(db)
        except Exception as exc:  # noqa: BLE001
            # Same rationale as _run_due_source above: a query failure here must
            # not crash the daemon thread. Logged and the next tick tries again.
            logger.error("Scheduler failed to query due sources: %s", exc)
            continue
        finally:
            db.close()

        for source in due_sources:
            if stop_event.is_set():
                break
            logger.info("Running scheduled scrape for source %d (%s)", source.id, source.name)
            _run_due_source(source.id)

    logger.info("Generator scheduler stopped")


_stop_event: threading.Event | None = None
_thread: threading.Thread | None = None


def start_scheduler() -> None:
    """Start the background scheduler thread. Idempotent."""
    global _stop_event, _thread

    if _thread and _thread.is_alive():
        return

    _stop_event = threading.Event()
    _thread = threading.Thread(
        target=_scheduler_loop,
        args=(_stop_event,),
        daemon=True,
        name="generator-scheduler",
    )
    _thread.start()


def stop_scheduler() -> None:
    """Signal the scheduler thread to stop and wait for it."""
    global _stop_event, _thread

    if not _stop_event or not _thread:
        return

    _stop_event.set()
    _thread.join(timeout=SCHEDULER_JOIN_TIMEOUT_SECONDS)
    _stop_event = None
    _thread = None
