"""Create the topics the events use (the broker doesn't auto-create them).

compose.yaml turns auto-creation off so a typo in a topic name fails loudly
instead of quietly writing to a new topic with default settings. The
aggregator calls ensure_topics() on start; it is idempotent.
"""

import logging

from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic

from .constants import (
    ADMIN_TIMEOUT_SECONDS,
    DLQ_PARTITIONS,
    DLQ_RETENTION_MS,
    LOG_EVENT_TOPIC_CREATED,
    POST_EVENTS_DLQ_TOPIC,
    POST_EVENTS_PARTITIONS,
    POST_EVENTS_RETENTION_MS,
    POST_EVENTS_TOPIC,
    REPLICATION_FACTOR,
)

logger = logging.getLogger(__name__)


def topic_specs() -> list[NewTopic]:
    return [
        NewTopic(
            POST_EVENTS_TOPIC,
            num_partitions=POST_EVENTS_PARTITIONS,
            replication_factor=REPLICATION_FACTOR,
            config={"retention.ms": str(POST_EVENTS_RETENTION_MS)},
        ),
        NewTopic(
            POST_EVENTS_DLQ_TOPIC,
            num_partitions=DLQ_PARTITIONS,
            replication_factor=REPLICATION_FACTOR,
            config={"retention.ms": str(DLQ_RETENTION_MS)},
        ),
    ]


def ensure_topics(admin: AdminClient) -> list[str]:
    """Create any missing topic; returns the names it created."""
    futures = admin.create_topics(topic_specs(), request_timeout=ADMIN_TIMEOUT_SECONDS)
    created = []
    for name, future in futures.items():
        try:
            future.result(timeout=ADMIN_TIMEOUT_SECONDS)
        except KafkaException as exc:
            if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise
            continue
        logger.info(LOG_EVENT_TOPIC_CREATED, extra={"topic": name})
        created.append(name)
    return created
