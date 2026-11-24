"""Fixtures for app/engagement/ tests.

The Kafka clients are the external boundary, so the unit tests replace them
with small recording fakes; tests/kafka/ runs the same code against a real
broker.
"""

import json
from collections.abc import Callable
from contextlib import contextmanager

import pytest
from confluent_kafka import Message

from app.engagement.constants import POST_EVENTS_TOPIC
from app.engagement.schema import PostEvent, PostEventType


@pytest.fixture()
def sessions(db_session) -> Callable:
    """Hands out the test session (not closed: the test still reads through it)."""

    @contextmanager
    def _factory():
        yield db_session

    return _factory


def event(
    event_type: PostEventType = PostEventType.LIKED,
    post_id: int = 1,
    occurred_at: float = 1_000_000.0,
    event_id: str | None = None,
    user_id: int | None = 1,
) -> PostEvent:
    return PostEvent(
        event_id=event_id or f"{event_type}-{post_id}-{occurred_at}",
        type=event_type,
        post_id=post_id,
        user_id=user_id,
        occurred_at=occurred_at,
    )


def message(value: bytes | str | dict, offset: int = 7, partition: int = 2) -> Message:
    if isinstance(value, dict):
        value = json.dumps(value)
    if isinstance(value, str):
        value = value.encode()
    return Message(
        topic=POST_EVENTS_TOPIC, partition=partition, offset=offset, key=b"1", value=value
    )
