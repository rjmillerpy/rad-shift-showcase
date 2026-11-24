"""The engagement aggregator: consumes post-events, maintains trending scores.

A separate process (compose service `aggregator`, same image as the API):

    python -m app.engagement.aggregator

It is its own consumer group, so it reads every event at its own pace
without affecting the API or any other consumer; a second group (say, a
notifications service) would get its own copy of the stream. That is the
difference from SQS (item 28), where one message goes to one worker and is
then deleted.

Delivery is at least once. For each message:
  * parsed and applied: the score and the event id commit together, then
    the offset is committed;
  * unparseable: copied to the dead-letter topic with the error, then the
    offset is committed (retrying can't fix it);
  * database error: nothing is committed; the consumer seeks back and
    retries the same message after a pause, so nothing is skipped.

Prometheus scrapes :9102 for events processed and consumer lag (how far the
group is behind the newest event): the health metric for any consumer.
"""

import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from enum import StrEnum

from confluent_kafka import Consumer, Message, Producer, TopicPartition
from confluent_kafka.admin import AdminClient
from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, start_http_server
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .constants import (
    AGGREGATOR_METRICS_PORT,
    CONSUMER_CLIENT_ID,
    CONSUMER_CONFIG,
    CONSUMER_GROUP,
    DLQ_FLUSH_TIMEOUT_SECONDS,
    ERROR_BACKOFF_SECONDS,
    HEADER_ERROR,
    HEADER_SOURCE,
    KAFKA_BOOTSTRAP_SERVERS_ENV_VAR,
    LAG_REPORT_INTERVAL_SECONDS,
    LOG_EVENT_APPLIED,
    LOG_EVENT_CONSUME_ERROR,
    LOG_EVENT_DB_FAILED,
    LOG_EVENT_DEAD_LETTERED,
    LOG_EVENT_PRUNED,
    LOG_EVENT_STARTED,
    LOG_EVENT_STOPPED,
    MAX_ERROR_HEADER_CHARS,
    POLL_TIMEOUT_SECONDS,
    POST_EVENTS_DLQ_TOPIC,
    POST_EVENTS_TOPIC,
    PROCESSED_EVENT_RETENTION_SECONDS,
    PRUNE_INTERVAL_SECONDS,
    WATERMARK_TIMEOUT_SECONDS,
)
from .schema import PostEvent
from .topics import ensure_topics
from .trending import apply_event, prune_processed

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]
# Committed offset reported by Kafka for a partition the group never committed.
NO_OFFSET = -1001


class Outcome(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    DEAD_LETTERED = "dead_lettered"
    RETRY = "retry"


class AggregatorMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self._processed = Counter(
            "post_events_processed",
            "Post events the aggregator handled, by outcome.",
            ["outcome"],
            registry=registry,
        )
        self._lag = Gauge(
            "kafka_consumer_lag",
            "Events in the partition the group hasn't committed yet.",
            ["topic", "partition"],
            registry=registry,
        )

    def processed(self, outcome: Outcome) -> None:
        self._processed.labels(outcome=outcome.value).inc()

    def lag(self, topic: str, partition: int, events: int) -> None:
        self._lag.labels(topic=topic, partition=str(partition)).set(events)


AGGREGATOR_METRICS = AggregatorMetrics(REGISTRY)


def _origin(message: Message) -> TopicPartition:
    """The topic, partition and offset a consumed message came from."""
    topic, partition, offset = message.topic(), message.partition(), message.offset()
    if topic is None or partition is None or offset is None:
        raise ValueError("not a consumed message: it has no topic, partition or offset")
    return TopicPartition(topic, partition, offset)


def _dead_letter(message: Message, error: str, dlq: Producer) -> bool:
    """Copy the message to the dead-letter topic; True once Kafka has it."""
    dlq.produce(
        POST_EVENTS_DLQ_TOPIC,
        value=message.value(),
        key=message.key(),
        headers={
            HEADER_ERROR: error[:MAX_ERROR_HEADER_CHARS],
            HEADER_SOURCE: f"{message.topic()}/{message.partition()}/{message.offset()}",
        },
    )
    return dlq.flush(DLQ_FLUSH_TIMEOUT_SECONDS) == 0


def handle(message: Message, sessions: SessionFactory, dlq: Producer) -> Outcome:
    """Process one message. RETRY means: don't commit, read it again."""
    try:
        event = PostEvent.model_validate_json(message.value() or b"")
    except ValidationError as exc:
        if not _dead_letter(message, str(exc), dlq):
            return Outcome.RETRY
        logger.warning(LOG_EVENT_DEAD_LETTERED, extra={"offset": message.offset()})
        return Outcome.DEAD_LETTERED
    try:
        with sessions() as db:
            applied = apply_event(db, event)
    except SQLAlchemyError:
        logger.exception(LOG_EVENT_DB_FAILED, extra={"event_id": event.event_id})
        return Outcome.RETRY
    if not applied:
        return Outcome.DUPLICATE
    logger.debug(LOG_EVENT_APPLIED, extra={"type": event.type, "post_id": event.post_id})
    return Outcome.APPLIED


def consume_one(
    consumer: Consumer,
    sessions: SessionFactory,
    dlq: Producer,
    stop: threading.Event,
    metrics: AggregatorMetrics = AGGREGATOR_METRICS,
) -> Outcome | None:
    """Poll once and handle what arrives; None when nothing did."""
    message = consumer.poll(POLL_TIMEOUT_SECONDS)
    if message is None:
        return None
    if message.error():
        logger.warning(LOG_EVENT_CONSUME_ERROR, extra={"error": str(message.error())})
        return None
    outcome = handle(message, sessions, dlq)
    metrics.processed(outcome)
    if outcome is Outcome.RETRY:
        consumer.seek(_origin(message))
        stop.wait(ERROR_BACKOFF_SECONDS)
        return outcome
    consumer.commit(message=message, asynchronous=False)
    return outcome


def report_lag(consumer: Consumer, metrics: AggregatorMetrics = AGGREGATOR_METRICS) -> int:
    """Set the lag gauge for every assigned partition; returns the total."""
    assigned = consumer.assignment()
    if not assigned:
        return 0
    total = 0
    for committed in consumer.committed(assigned, timeout=WATERMARK_TIMEOUT_SECONDS):
        low, high = consumer.get_watermark_offsets(
            TopicPartition(committed.topic, committed.partition),
            timeout=WATERMARK_TIMEOUT_SECONDS,
            cached=False,
        )
        start = low if committed.offset == NO_OFFSET else committed.offset
        lag = max(high - start, 0)
        metrics.lag(committed.topic, committed.partition, lag)
        total += lag
    return total


def prune(sessions: SessionFactory, now: float) -> int:
    with sessions() as db:
        return prune_processed(db, now - PROCESSED_EVENT_RETENTION_SECONDS)


def run(
    consumer: Consumer,
    sessions: SessionFactory,
    dlq: Producer,
    stop: threading.Event,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Consume until stopped, reporting lag and pruning on their intervals."""
    consumer.subscribe([POST_EVENTS_TOPIC])
    next_lag_report = next_prune = clock()
    try:
        while not stop.is_set():
            consume_one(consumer, sessions, dlq, stop)
            if clock() >= next_lag_report:
                report_lag(consumer)
                next_lag_report = clock() + LAG_REPORT_INTERVAL_SECONDS
            if clock() >= next_prune:
                pruned = prune(sessions, time.time())
                if pruned:
                    logger.info(LOG_EVENT_PRUNED, extra={"events": pruned})
                next_prune = clock() + PRUNE_INTERVAL_SECONDS
    finally:
        # Commits nothing new (offsets are committed per message) and leaves
        # the group at once, so another instance takes the partitions over
        # without waiting for a session timeout.
        consumer.close()
        dlq.flush(DLQ_FLUSH_TIMEOUT_SECONDS)


def build_consumer(bootstrap_servers: str, group_id: str = CONSUMER_GROUP) -> Consumer:
    """A consumer in `group_id`; another group gets its own copy of every event."""
    return Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "client.id": CONSUMER_CLIENT_ID,
            **CONSUMER_CONFIG,
            "logger": logging.getLogger("confluent_kafka.consumer"),
        }
    )


def build_dead_letter_producer(bootstrap_servers: str) -> Producer:
    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": f"{CONSUMER_CLIENT_ID}-dlq",
            "enable.idempotence": True,
            "logger": logging.getLogger("confluent_kafka.producer"),
        }
    )


def main() -> None:  # pragma: no cover - process wiring; the parts are tested
    # Every table the ORM may touch must be mapped before the first query.
    import app.auth.models  # noqa: F401
    import app.posts.models  # noqa: F401
    from app.common.db import SessionLocal

    bootstrap_servers = os.environ[KAFKA_BOOTSTRAP_SERVERS_ENV_VAR]
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())

    ensure_topics(AdminClient({"bootstrap.servers": bootstrap_servers}))
    start_http_server(AGGREGATOR_METRICS_PORT)
    logger.info(LOG_EVENT_STARTED, extra={"group": CONSUMER_GROUP})
    run(
        build_consumer(bootstrap_servers),
        SessionLocal,
        build_dead_letter_producer(bootstrap_servers),
        stop,
    )
    logger.info(LOG_EVENT_STOPPED)


if __name__ == "__main__":  # pragma: no cover
    main()
