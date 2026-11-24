"""Tests for app/engagement/topics.py: topics are created once, with their settings.

The admin client is the external boundary; tests/kafka/ creates the topics
on a real broker.
"""

from concurrent.futures import Future

import pytest
from confluent_kafka import KafkaError, KafkaException

from app.engagement.constants import (
    DLQ_RETENTION_MS,
    POST_EVENTS_DLQ_TOPIC,
    POST_EVENTS_PARTITIONS,
    POST_EVENTS_RETENTION_MS,
    POST_EVENTS_TOPIC,
)
from app.engagement.topics import ensure_topics, topic_specs


class FakeAdmin:
    def __init__(self, errors: dict[str, int] | None = None) -> None:
        self.errors = errors or {}
        self.requested: list = []

    def create_topics(self, new_topics, request_timeout):
        self.requested = new_topics
        futures = {}
        for topic in new_topics:
            future: Future = Future()
            code = self.errors.get(topic.topic)
            if code is None:
                future.set_result(None)
            else:
                future.set_exception(KafkaException(KafkaError(code)))
            futures[topic.topic] = future
        return futures


def test_creates_both_topics_with_their_partitions_and_retention():
    specs = {spec.topic: spec for spec in topic_specs()}

    assert specs[POST_EVENTS_TOPIC].num_partitions == POST_EVENTS_PARTITIONS
    assert specs[POST_EVENTS_TOPIC].config == {"retention.ms": str(POST_EVENTS_RETENTION_MS)}
    assert specs[POST_EVENTS_DLQ_TOPIC].config == {"retention.ms": str(DLQ_RETENTION_MS)}
    assert ensure_topics(FakeAdmin()) == [POST_EVENTS_TOPIC, POST_EVENTS_DLQ_TOPIC]


def test_existing_topics_are_left_alone():
    admin = FakeAdmin({POST_EVENTS_TOPIC: KafkaError.TOPIC_ALREADY_EXISTS})

    assert ensure_topics(admin) == [POST_EVENTS_DLQ_TOPIC]


def test_any_other_error_is_raised():
    admin = FakeAdmin({POST_EVENTS_TOPIC: KafkaError.TOPIC_AUTHORIZATION_FAILED})

    with pytest.raises(KafkaException):
        ensure_topics(admin)
