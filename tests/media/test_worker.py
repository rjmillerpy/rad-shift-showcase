"""Tests for app/media/worker.py: starting, stopping and surviving errors."""

import threading
import time

import pytest
from botocore.exceptions import EndpointConnectionError

from app.media import worker
from app.media.constants import (
    LOG_EVENT_POLL_FAILED,
    MEDIA_RESULTS_QUEUE_URL_ENV_VAR,
    WORKER_JOIN_TIMEOUT_SECONDS,
)

QUEUE_URL = "https://sqs.us-east-2.amazonaws.com/123456789012/radshift-media-results"


def test_the_region_comes_from_the_queue_url():
    assert worker.queue_region(QUEUE_URL) == "us-east-2"


def test_the_client_talks_to_that_region():
    assert worker.sqs_client(QUEUE_URL).meta.region_name == "us-east-2"


class TestStart:
    def test_nothing_starts_without_a_queue(self, monkeypatch):
        monkeypatch.delenv(MEDIA_RESULTS_QUEUE_URL_ENV_VAR, raising=False)
        assert worker.start() is False

    def test_starts_once_and_stops_without_waiting_for_the_long_poll(
        self, results_queue, monkeypatch
    ):
        _, queue_url = results_queue
        monkeypatch.setenv(MEDIA_RESULTS_QUEUE_URL_ENV_VAR, queue_url)
        assert worker.start() is True
        assert worker.start() is False  # already running
        polling = [t for t in threading.enumerate() if t.name == "media-results"]
        assert len(polling) == 1 and polling[0].daemon
        started = time.monotonic()
        worker.stop()
        assert time.monotonic() - started < WORKER_JOIN_TIMEOUT_SECONDS + 1

    def test_stop_without_start_is_harmless(self):
        worker.stop()


class _UnreachableSQS:
    """An SQS client whose network is down (the boundary, not our code)."""

    def __init__(self, stop: threading.Event) -> None:
        self.calls = 0
        self._stop = stop

    def receive_message(self, **_kwargs):
        self.calls += 1
        self._stop.set()  # one failure is enough to observe
        raise EndpointConnectionError(endpoint_url=QUEUE_URL)


def test_an_aws_error_is_logged_and_the_loop_backs_off(caplog, monkeypatch):
    monkeypatch.setattr(worker, "ERROR_BACKOFF_SECONDS", 0)
    stop = threading.Event()
    sqs = _UnreachableSQS(stop)
    started = time.monotonic()
    worker.run(sqs, QUEUE_URL, stop)
    assert sqs.calls == 1
    assert time.monotonic() - started < 5
    assert any(r.getMessage() == LOG_EVENT_POLL_FAILED for r in caplog.records)


def test_a_stopped_worker_never_polls():
    stop = threading.Event()
    stop.set()
    sqs = _UnreachableSQS(stop)
    worker.run(sqs, QUEUE_URL, stop)
    assert sqs.calls == 0


@pytest.fixture(autouse=True)
def _never_leave_a_worker_running():
    yield
    worker.stop()
