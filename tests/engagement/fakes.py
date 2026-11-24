"""A stand-in for confluent_kafka.Producer (the external boundary)."""

from collections.abc import Callable

from confluent_kafka import KafkaError, Message

from app.engagement.constants import POST_EVENTS_TOPIC
from app.engagement.schema import PostEvent


class RecordingProducer:
    """Records produce() calls; delivers them on poll()/flush() like librdkafka."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.raise_on_produce: Exception | None = None
        self.delivery_error: KafkaError | None = None
        self.undelivered_at_flush = 0
        self._callbacks: list[tuple[Callable, Message]] = []

    def produce(self, topic, value=None, key=None, on_delivery=None, headers=None) -> None:
        if self.raise_on_produce is not None:
            raise self.raise_on_produce
        self.sent.append({"topic": topic, "value": value, "key": key, "headers": headers})
        if on_delivery is not None:
            self._callbacks.append((on_delivery, Message(topic=topic, value=value, key=key)))

    def poll(self, timeout: float) -> int:
        callbacks, self._callbacks = self._callbacks, []
        for callback, message in callbacks:
            callback(self.delivery_error, message)
        return len(callbacks)

    def flush(self, timeout: float) -> int:
        self.poll(timeout)
        return self.undelivered_at_flush

    def events(self) -> list[PostEvent]:
        return [
            PostEvent.model_validate_json(m["value"])
            for m in self.sent
            if m["topic"] == POST_EVENTS_TOPIC
        ]
