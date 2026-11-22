"""Fixtures for app/media/ tests: moto's in-memory SQS and a session factory on the test DB."""

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")

BUCKET = "radshift-test-media"


@pytest.fixture()
def results_queue() -> Iterator[tuple[object, str]]:
    with mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-2")
        url = sqs.create_queue(QueueName="radshift-test-results")["QueueUrl"]
        yield sqs, url


@pytest.fixture()
def send_result(results_queue) -> Callable[..., None]:
    sqs, url = results_queue

    def _send(body: dict | str) -> None:
        sqs.send_message(
            QueueUrl=url, MessageBody=body if isinstance(body, str) else json.dumps(body)
        )

    return _send


@pytest.fixture()
def session_factory(db_session) -> Callable:
    """Hands out the test session (not closed: the test still reads through it)."""

    @contextmanager
    def _factory():
        yield db_session

    return _factory


def result_for(key: str, widths: tuple[int, ...] = (480, 1280), width: int = 2000) -> dict:
    stem = key.rsplit(".", 1)[0]
    return {
        "bucket": BUCKET,
        "source_key": key,
        "width": width,
        "variants": {str(w): f"variants/{stem}-{w}.webp" for w in widths},
    }


def url(key: str) -> str:
    return f"https://{BUCKET}.s3.amazonaws.com/{key}"
