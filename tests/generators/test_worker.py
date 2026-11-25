"""app/generators/worker.py: the scheduler as a single process."""

import threading

from app.generators import scheduler
from app.generators.worker import EXIT_SCHEDULER_DIED, EXIT_STOPPED, run


def test_runs_the_scheduler_until_stopped():
    stop = threading.Event()
    seen_running: list[bool] = []

    def stop_soon():
        seen_running.append(scheduler.is_running())
        stop.set()

    timer = threading.Timer(0.2, stop_soon)
    timer.start()

    assert run(stop, check_seconds=0.05) == EXIT_STOPPED
    assert seen_running == [True]
    assert not scheduler.is_running(), "stopped on the way out"


def test_exits_non_zero_when_the_scheduler_thread_is_gone():
    stop = threading.Event()
    threading.Timer(0.2, scheduler.stop_scheduler).start()

    assert run(stop, check_seconds=0.05) == EXIT_SCHEDULER_DIED
    assert not stop.is_set()
