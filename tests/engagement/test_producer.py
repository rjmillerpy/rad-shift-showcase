"""Tests for app/engagement/producer.py: publishing never blocks or breaks a request."""

import logging

import pytest
from confluent_kafka import KafkaError, KafkaException
from prometheus_client import REGISTRY

from app.engagement import producer
from app.engagement.constants import (
    KAFKA_BOOTSTRAP_SERVERS_ENV_VAR,
    LOG_EVENT_DELIVERY_FAILED,
    LOG_EVENT_PUBLISH_DROPPED,
    LOG_EVENT_UNDELIVERED_AT_STOP,
    POST_EVENTS_TOPIC,
)
from app.engagement.schema import PostEventType

from .fakes import RecordingProducer


def published_count(event_type: str, outcome: str) -> float:
    value = REGISTRY.get_sample_value(
        "post_events_published_total", {"type": event_type, "outcome": outcome}
    )
    return value or 0.0


class TestStart:
    def test_without_brokers_nothing_starts(self, monkeypatch):
        monkeypatch.delenv(KAFKA_BOOTSTRAP_SERVERS_ENV_VAR, raising=False)

        assert producer.start() is False
        producer.emit(PostEventType.LIKED, 1, 1)  # a no-op, not an error

    def test_with_brokers_a_real_client_is_built(self, monkeypatch):
        # librdkafka connects lazily, so no broker is needed to build one.
        monkeypatch.setenv(KAFKA_BOOTSTRAP_SERVERS_ENV_VAR, "127.0.0.1:1")

        assert producer.start() is True
        producer.stop()


class TestPublish:
    def test_an_event_goes_to_the_topic_keyed_by_post(self, published):
        producer.emit(PostEventType.REPOSTED, post_id=12, user_id=3)

        (sent,) = published.sent
        assert sent["topic"] == POST_EVENTS_TOPIC
        assert sent["key"] == b"12"
        (event,) = published.events()
        assert (event.type, event.post_id, event.user_id) == (PostEventType.REPOSTED, 12, 3)

    def test_delivery_is_counted(self, published):
        before = published_count("post.saved", "delivered")

        producer.emit(PostEventType.SAVED, 1, 1)
        producer.emit(PostEventType.SAVED, 2, 1)  # its poll() delivers the first
        published.poll(0)

        assert published_count("post.saved", "delivered") == before + 2

    def test_a_failed_delivery_is_logged_and_counted(self, published, caplog):
        published.delivery_error = KafkaError(KafkaError._MSG_TIMED_OUT)
        before = published_count("post.liked", "failed")

        with caplog.at_level(logging.WARNING):
            producer.emit(PostEventType.LIKED, 1, 1)
            published.poll(0)

        assert published_count("post.liked", "failed") == before + 1
        assert LOG_EVENT_DELIVERY_FAILED in caplog.messages

    @pytest.mark.parametrize(
        "error",
        [BufferError("queue full"), KafkaException(KafkaError(KafkaError._UNKNOWN_TOPIC))],
        ids=["queue-full", "rejected"],
    )
    def test_an_event_that_cant_be_queued_is_dropped_not_raised(self, published, caplog, error):
        published.raise_on_produce = error
        before = published_count("post.unliked", "dropped")

        with caplog.at_level(logging.WARNING):
            producer.emit(PostEventType.UNLIKED, 1, 1)

        assert published_count("post.unliked", "dropped") == before + 1
        assert LOG_EVENT_PUBLISH_DROPPED in caplog.messages


class TestStop:
    def test_stop_flushes_and_stops_publishing(self):
        fake = RecordingProducer()
        producer.start(fake)

        producer.stop()
        producer.emit(PostEventType.LIKED, 1, 1)

        assert fake.sent == []

    def test_events_still_queued_at_stop_are_reported(self, caplog):
        fake = RecordingProducer()
        fake.undelivered_at_flush = 3
        producer.start(fake)

        with caplog.at_level(logging.WARNING):
            producer.stop()

        assert LOG_EVENT_UNDELIVERED_AT_STOP in caplog.messages

    def test_stopping_twice_is_harmless(self):
        producer.stop()
        producer.stop()


def test_a_delivery_report_it_cant_read_is_counted_as_unknown(published):
    """The callback runs inside poll(), on the request's thread: it must never raise."""
    before = published_count("unknown", "delivered")

    published.produce(POST_EVENTS_TOPIC, value=b"not an event", on_delivery=producer._on_delivery)
    published.poll(0)

    assert published_count("unknown", "delivered") == before + 1
