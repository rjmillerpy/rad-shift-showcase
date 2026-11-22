"""The background thread that polls the results queue (app/media/service.py).

Started by the app's lifespan when MEDIA_RESULTS_QUEUE_URL is set; without
it nothing runs and posts keep serving their originals only.
"""

import logging
import os
import threading
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.exc import SQLAlchemyError

from app.common.db import SessionLocal

from .constants import (
    ERROR_BACKOFF_SECONDS,
    LOG_EVENT_POLL_FAILED,
    MEDIA_RESULTS_QUEUE_URL_ENV_VAR,
    SQS_CONNECT_TIMEOUT_SECONDS,
    SQS_READ_TIMEOUT_SECONDS,
    WORKER_JOIN_TIMEOUT_SECONDS,
    WORKER_THREAD_NAME,
)
from .service import SQSClient, poll_once

logger = logging.getLogger(__name__)


def queue_region(queue_url: str) -> str:
    """us-east-2 from https://sqs.us-east-2.amazonaws.com/<account>/<name>."""
    return (urlparse(queue_url).hostname or "").split(".")[1]


def sqs_client(queue_url: str) -> SQSClient:
    return boto3.client(
        "sqs",
        region_name=queue_region(queue_url),
        config=Config(
            connect_timeout=SQS_CONNECT_TIMEOUT_SECONDS, read_timeout=SQS_READ_TIMEOUT_SECONDS
        ),
    )


def run(sqs: SQSClient, queue_url: str, stop: threading.Event) -> None:
    """Poll until stopped; an AWS or database error waits and tries again."""
    while not stop.is_set():
        try:
            poll_once(sqs, queue_url, SessionLocal)
        except (BotoCoreError, ClientError, SQLAlchemyError):
            logger.exception(LOG_EVENT_POLL_FAILED)
            stop.wait(ERROR_BACKOFF_SECONDS)


_stop: threading.Event | None = None
_thread: threading.Thread | None = None


def start() -> bool:
    """Start polling if a results queue is configured; returns whether it started."""
    global _stop, _thread
    queue_url = os.getenv(MEDIA_RESULTS_QUEUE_URL_ENV_VAR)
    if not queue_url or (_thread and _thread.is_alive()):
        return False
    _stop = threading.Event()
    _thread = threading.Thread(
        target=run,
        args=(sqs_client(queue_url), queue_url, _stop),
        daemon=True,
        name=WORKER_THREAD_NAME,
    )
    _thread.start()
    return True


def stop() -> None:
    """Signal the worker and wait for its current poll to finish."""
    global _stop, _thread
    if not _stop or not _thread:
        return
    _stop.set()
    _thread.join(timeout=WORKER_JOIN_TIMEOUT_SECONDS)
    _stop = None
    _thread = None
