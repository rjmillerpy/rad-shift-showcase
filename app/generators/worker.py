"""The generator scheduler as a process of its own: `python -m app.generators.worker`.

Kubernetes (deploy/helm/) scales the API across replicas, and a scheduler in
each would run every due source once per replica. So the scaled API runs
with GENERATOR_SCHEDULER_ENABLED=false and this worker runs as a single pod
(replicas 1, Recreate: the old pod stops before the new one starts).

Exits non-zero if the scheduler thread dies, so Kubernetes restarts it.
"""

import logging
import signal
import sys
import threading

from app.generators.constants import WORKER_CHECK_SECONDS
from app.generators.scheduler import is_running, start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

EXIT_STOPPED = 0
EXIT_SCHEDULER_DIED = 1


def run(stop: threading.Event, check_seconds: float = WORKER_CHECK_SECONDS) -> int:
    """Run the scheduler until `stop` is set; the exit code for the process."""
    start_scheduler()
    try:
        while not stop.wait(check_seconds):
            if not is_running():
                logger.error("Generator scheduler thread died")
                return EXIT_SCHEDULER_DIED
        return EXIT_STOPPED
    finally:
        stop_scheduler()


def main() -> None:  # pragma: no cover - process wiring; run() is tested
    import app.auth.models  # noqa: F401 - mapped before the first query
    import app.posts.models  # noqa: F401

    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    sys.exit(run(stop))


if __name__ == "__main__":  # pragma: no cover
    main()
