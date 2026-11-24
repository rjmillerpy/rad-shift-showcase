"""Tests for app/engagement/aggregator.py: commit after the work, dead-letter the unparseable,
retry on database errors.

The consumer is the external boundary, replaced by FakeConsumer (a partition
log with a committed offset); the database and the scoring run for real.
tests/kafka/ runs the same loop against a real broker.
"""

import threading

import pytest
from confluent_kafka import KafkaError, KafkaException, Message, TopicPartition
from prometheus_client import REGISTRY
from sqlalchemy.exc import OperationalError

from app.engagement.aggregator import (
    NO_OFFSET,
    AggregatorMetrics,
    Outcome,
    consume_one,
    handle,
    prune,
    report_lag,
    run,
)
from app.engagement.constants import (
    HEADER_ERROR,
    HEADER_SOURCE,
    LOG_EVENT_COMMIT_FAILED,
    LOG_EVENT_LAG_FAILED,
    LOG_EVENT_PRUNE_FAILED,
    LOG_EVENT_PRUNED,
    POST_EVENTS_DLQ_TOPIC,
    POST_EVENTS_TOPIC,
    PROCESSED_EVENT_RETENTION_SECONDS,
)
from app.engagement.models import PostTrending, ProcessedPostEvent
from app.engagement.schema import PostEventType

from .conftest import event, message
from .fakes import RecordingProducer

T0 = 1_000_000.0


class FakeConsumer:
    """One partition of post-events: a log, a read position and a committed offset."""

    def __init__(self, messages: list[Message] | None = None) -> None:
        self.log = list(messages or [])
        self.position = 0
        self.committed_offset = NO_OFFSET
        self.subscribed: list[str] = []
        self.seeks: list[TopicPartition] = []
        self.closed = False

    def subscribe(self, topics):
        self.subscribed = topics

    def poll(self, timeout):
        if self.position >= len(self.log):
            return None
        found = self.log[self.position]
        self.position += 1
        return found

    def seek(self, partition: TopicPartition):
        self.seeks.append(partition)
        self.position = next(i for i, m in enumerate(self.log) if m.offset() == partition.offset)

    def commit(self, message, asynchronous):
        assert asynchronous is False, "offsets are committed synchronously, after the work"
        self.committed_offset = message.offset() + 1

    def assignment(self):
        return [TopicPartition(POST_EVENTS_TOPIC, 0)]

    def committed(self, partitions, timeout):
        return [TopicPartition(POST_EVENTS_TOPIC, 0, self.committed_offset)]

    def get_watermark_offsets(self, partition, timeout, cached):
        return 0, len(self.log)

    def close(self):
        self.closed = True


class FailingDeadLetters(RecordingProducer):
    def flush(self, timeout):
        return 1  # still in the queue: Kafka never acknowledged it


@pytest.fixture()
def post(create_user, create_post):
    return create_post(user=create_user(username="author"))


@pytest.fixture()
def stop():
    return threading.Event()


def liked(post_id, offset=0, event_id=None):
    return message(
        event(PostEventType.LIKED, post_id, T0, event_id=event_id).model_dump_json(),
        offset=offset,
    )


class TestHandle:
    def test_an_event_is_applied(self, db_session, sessions, post):
        assert handle(liked(post.id), sessions, RecordingProducer()) is Outcome.APPLIED
        assert db_session.get(PostTrending, post.id).score == 1.0

    def test_a_redelivered_event_is_a_duplicate(self, sessions, post):
        handle(liked(post.id), sessions, RecordingProducer())

        assert handle(liked(post.id), sessions, RecordingProducer()) is Outcome.DUPLICATE

    @pytest.mark.parametrize(
        "value", [b"not json", b"", '{"type": "post.liked"}'], ids=["garbage", "empty", "partial"]
    )
    def test_an_unparseable_message_is_dead_lettered_with_its_error(self, sessions, value):
        dlq = RecordingProducer()

        assert handle(message(value, offset=41), sessions, dlq) is Outcome.DEAD_LETTERED

        (sent,) = dlq.sent
        assert sent["topic"] == POST_EVENTS_DLQ_TOPIC
        assert sent["value"] == (value.encode() if isinstance(value, str) else value)
        assert sent["headers"][HEADER_SOURCE] == f"{POST_EVENTS_TOPIC}/2/41"
        assert "validation error" in sent["headers"][HEADER_ERROR]

    def test_if_the_dead_letter_isnt_acknowledged_it_is_retried(self, sessions):
        assert handle(message(b"nope"), sessions, FailingDeadLetters()) is Outcome.RETRY

    def test_a_database_error_is_retried(self, post):
        def broken_sessions():
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

        assert handle(liked(post.id), broken_sessions, RecordingProducer()) is Outcome.RETRY


class TestConsumeOne:
    def test_nothing_to_read(self, sessions, stop):
        assert consume_one(FakeConsumer(), sessions, RecordingProducer(), stop) is None

    def test_the_offset_is_committed_after_the_work(self, db_session, sessions, stop, post):
        consumer = FakeConsumer([liked(post.id, offset=0)])

        assert consume_one(consumer, sessions, RecordingProducer(), stop) is Outcome.APPLIED

        assert consumer.committed_offset == 1
        assert db_session.get(ProcessedPostEvent, f"{PostEventType.LIKED}-{post.id}-{T0}")

    def test_a_dead_lettered_message_is_committed_too(self, sessions, stop):
        consumer = FakeConsumer([message(b"garbage", offset=0)])

        assert consume_one(consumer, sessions, RecordingProducer(), stop) is Outcome.DEAD_LETTERED
        assert consumer.committed_offset == 1

    def test_a_retry_rereads_the_same_message_and_commits_nothing(self, stop, post):
        consumer = FakeConsumer([liked(post.id, offset=0)])
        stop.set()  # skip the back-off pause

        def broken_sessions():
            raise OperationalError("SELECT 1", {}, Exception("down"))

        assert consume_one(consumer, broken_sessions, RecordingProducer(), stop) is Outcome.RETRY

        assert consumer.committed_offset == NO_OFFSET
        assert consumer.seeks == [TopicPartition(POST_EVENTS_TOPIC, 2, 0)]
        assert consumer.poll(0).offset() == 0, "the same message comes back"

    def test_a_consumer_error_is_skipped(self, sessions, stop):
        broken = Message(error=KafkaError(KafkaError._TRANSPORT))
        consumer = FakeConsumer([broken])

        assert consume_one(consumer, sessions, RecordingProducer(), stop) is None
        assert consumer.committed_offset == NO_OFFSET

    def test_outcomes_are_counted(self, sessions, stop, post):
        before = (
            REGISTRY.get_sample_value("post_events_processed_total", {"outcome": "applied"}) or 0.0
        )

        consume_one(FakeConsumer([liked(post.id)]), sessions, RecordingProducer(), stop)

        after = REGISTRY.get_sample_value("post_events_processed_total", {"outcome": "applied"})
        assert after == before + 1


class TestReportLag:
    def lag(self, metrics_registry):
        return metrics_registry.get_sample_value(
            "kafka_consumer_lag", {"topic": POST_EVENTS_TOPIC, "partition": "0"}
        )

    def test_lag_is_what_the_group_hasnt_committed(self, sessions, stop, post):
        from prometheus_client import CollectorRegistry

        registry = CollectorRegistry()
        metrics = AggregatorMetrics(registry)
        consumer = FakeConsumer([liked(post.id, offset=i, event_id=f"e{i}") for i in range(3)])

        assert report_lag(consumer, metrics) == 3, "nothing committed yet: the whole log"
        consume_one(consumer, sessions, RecordingProducer(), stop, metrics)

        assert report_lag(consumer, metrics) == 2
        assert self.lag(registry) == 2

    def test_no_partitions_no_lag(self):
        consumer = FakeConsumer()
        consumer.assignment = lambda: []

        assert report_lag(consumer) == 0


class TestRun:
    def test_consumes_until_stopped_then_closes(self, db_session, sessions, stop, post):
        consumer = FakeConsumer([liked(post.id, offset=i, event_id=f"run{i}") for i in range(3)])
        dlq = RecordingProducer()
        original_poll = consumer.poll

        def poll_then_stop(timeout):
            found = original_poll(timeout)
            if found is None:
                stop.set()
            return found

        consumer.poll = poll_then_stop

        run(consumer, sessions, dlq, stop)

        assert consumer.subscribed == [POST_EVENTS_TOPIC]
        assert consumer.committed_offset == 3
        assert db_session.get(PostTrending, post.id).score == 3.0
        assert consumer.closed

    def test_old_event_ids_are_pruned_on_the_first_pass(self, db_session, sessions, stop, caplog):
        db_session.add(ProcessedPostEvent(event_id="ancient", processed_at=1.0))
        db_session.commit()
        consumer = FakeConsumer()
        consumer.poll = lambda timeout: stop.set()

        with caplog.at_level("INFO"):
            run(consumer, sessions, RecordingProducer(), stop)

        assert db_session.get(ProcessedPostEvent, "ancient") is None
        assert LOG_EVENT_PRUNED in caplog.messages


def test_a_retry_needs_to_know_where_the_message_came_from(stop):
    def broken_sessions():
        raise OperationalError("SELECT 1", {}, Exception("down"))

    stop.set()
    consumer = FakeConsumer([Message(value=event().model_dump_json().encode())])

    with pytest.raises(ValueError, match="not a consumed message"):
        consume_one(consumer, broken_sessions, RecordingProducer(), stop)


def test_prune_keeps_ids_that_can_still_be_replayed(db_session, sessions):
    now = T0 + PROCESSED_EVENT_RETENTION_SECONDS + 100
    db_session.add_all(
        [
            ProcessedPostEvent(event_id="replayable", processed_at=now - 10),
            ProcessedPostEvent(event_id="expired", processed_at=T0),
        ]
    )
    db_session.commit()

    assert prune(sessions, now) == 1
    assert db_session.get(ProcessedPostEvent, "replayable") is not None


class TestBrokerOutage:
    """Found in a drill: with Kafka stopped, the lag report raised and the process died."""

    def broker_down(self, *args, **kwargs):
        raise KafkaException(KafkaError(KafkaError._TRANSPORT))

    def test_a_failed_commit_is_logged_and_the_work_kept(
        self, db_session, sessions, stop, post, caplog
    ):
        consumer = FakeConsumer([liked(post.id)])
        consumer.commit = self.broker_down

        with caplog.at_level("WARNING"):
            outcome = consume_one(consumer, sessions, RecordingProducer(), stop)

        assert outcome is Outcome.APPLIED
        assert db_session.get(PostTrending, post.id).score == 1.0
        assert LOG_EVENT_COMMIT_FAILED in caplog.messages

    def test_the_loop_survives_lag_reports_and_pruning_failing(self, sessions, stop, caplog):
        consumer = FakeConsumer()
        consumer.committed = self.broker_down
        polls = []

        def poll(timeout):
            polls.append(timeout)
            if len(polls) == 2:
                stop.set()

        consumer.poll = poll

        def broken_sessions():
            raise OperationalError("DELETE", {}, Exception("down"))

        with caplog.at_level("WARNING"):
            run(
                consumer,
                broken_sessions,
                RecordingProducer(),
                stop,
                clock=iter(range(0, 10**6, 10**5)).__next__,
            )

        assert len(polls) == 2, "still polling after both failures"
        assert LOG_EVENT_LAG_FAILED in caplog.messages
        assert LOG_EVENT_PRUNE_FAILED in caplog.messages
        assert consumer.closed
