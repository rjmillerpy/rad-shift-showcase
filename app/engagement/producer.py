"""Publishing post events from the API (roadmap item 29b).

Started by the app's lifespan when KAFKA_BOOTSTRAP_SERVERS is set. Publishing
never blocks or fails a request: produce() only queues the event, librdkafka
sends it in the background, and anything that can't be queued or delivered
is logged and counted (post_events_published_total), not raised.

Events are published after the database commit, so a crash between the two
loses the event (the change itself is safe). That's acceptable for a
trending score; when every event must arrive, the fix is a transactional
outbox: write the event to a table in the same transaction and have a relay
publish it.
"""

import logging
import os
from typing import Protocol

from confluent_kafka import KafkaError, KafkaException, Message, Producer
from prometheus_client import REGISTRY, CollectorRegistry, Counter

from .constants import (
    FLUSH_TIMEOUT_SECONDS,
    KAFKA_BOOTSTRAP_SERVERS_ENV_VAR,
    LOG_EVENT_DELIVERY_FAILED,
    LOG_EVENT_PUBLISH_DROPPED,
    LOG_EVENT_UNDELIVERED_AT_STOP,
    POST_EVENTS_TOPIC,
    PRODUCER_CLIENT_ID,
    PRODUCER_CONFIG,
)
from .schema import PostEvent, PostEventType

logger = logging.getLogger(__name__)

OUTCOME_QUEUED = "queued"
OUTCOME_DELIVERED = "delivered"
OUTCOME_FAILED = "failed"  # queued, but Kafka never acknowledged it
OUTCOME_DROPPED = "dropped"  # never queued (queue full, or rejected)


class EventProducer(Protocol):
    """The part of confluent_kafka.Producer used here."""

    def produce(self, topic: str, value: bytes, key: bytes, on_delivery: object) -> None: ...

    def poll(self, timeout: float) -> int: ...

    def flush(self, timeout: float) -> int: ...


class PublishMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        # prometheus_client appends _total on export.
        self._events = Counter(
            "post_events_published",
            "Post events the API tried to publish to Kafka, by type and outcome.",
            ["type", "outcome"],
            registry=registry,
        )

    def count(self, event_type: str, outcome: str) -> None:
        self._events.labels(type=event_type, outcome=outcome).inc()


# One per process, like app.metrics.service.REQUEST_METRICS.
PUBLISH_METRICS = PublishMetrics(REGISTRY)

_producer: EventProducer | Producer | None = None


def build_producer(bootstrap_servers: str) -> Producer:
    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": PRODUCER_CLIENT_ID,
            **PRODUCER_CONFIG,
            # librdkafka's own messages go through the app's JSON logs.
            "logger": logging.getLogger("confluent_kafka.producer"),
        }
    )


def start(producer: EventProducer | Producer | None = None) -> bool:
    """Start publishing; returns whether it started (no brokers configured: no)."""
    global _producer
    if producer is None:
        bootstrap_servers = os.getenv(KAFKA_BOOTSTRAP_SERVERS_ENV_VAR)
        if not bootstrap_servers:
            return False
        producer = build_producer(bootstrap_servers)
    _producer = producer
    return True


def stop() -> None:
    """Send what's queued (briefly), then stop publishing."""
    global _producer
    if _producer is None:
        return
    undelivered = _producer.flush(FLUSH_TIMEOUT_SECONDS)
    if undelivered:
        logger.warning(LOG_EVENT_UNDELIVERED_AT_STOP, extra={"events": undelivered})
    _producer = None


def _on_delivery(error: KafkaError | None, message: Message) -> None:
    event_type = _event_type(message)
    if error is None:
        PUBLISH_METRICS.count(event_type, OUTCOME_DELIVERED)
        return
    PUBLISH_METRICS.count(event_type, OUTCOME_FAILED)
    logger.warning(LOG_EVENT_DELIVERY_FAILED, extra={"error": str(error), "type": event_type})


def _event_type(message: Message) -> str:
    """The event type, read back from the message (the callback gets nothing else)."""
    value = message.value()
    try:
        return PostEvent.model_validate_json(value or b"").type.value
    except ValueError:
        return "unknown"


def publish(event: PostEvent) -> None:
    """Queue one event; a no-op when publishing isn't started."""
    if _producer is None:
        return
    try:
        _producer.produce(
            POST_EVENTS_TOPIC,
            value=event.model_dump_json().encode(),
            key=str(event.post_id).encode(),
            on_delivery=_on_delivery,
        )
    except (BufferError, KafkaException) as exc:
        PUBLISH_METRICS.count(event.type.value, OUTCOME_DROPPED)
        logger.warning(LOG_EVENT_PUBLISH_DROPPED, extra={"error": str(exc), "type": event.type})
        return
    PUBLISH_METRICS.count(event.type.value, OUTCOME_QUEUED)
    # Serves delivery callbacks for earlier events; never waits.
    _producer.poll(0)


def emit(event_type: PostEventType, post_id: int, user_id: int | None) -> None:
    """Publish a new event for a change the caller has just committed."""
    publish(PostEvent.new(event_type, post_id, user_id))
