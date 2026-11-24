"""The post-event path on a real broker: API producer → topic → aggregator → score.

What a fake can't show: partitioning by key, committed offsets surviving a
restart, a new group replaying the topic, and dead letters landing on Kafka.

The broker is shared by the session, so a new consumer group also reads
earlier tests' events; drain() consumes until the group has caught up.
Events for posts this test's database doesn't have are skipped (no_post).
"""

import threading
import time
import uuid

import pytest
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient

from app.engagement import producer
from app.engagement.aggregator import (
    NO_OFFSET,
    Outcome,
    build_consumer,
    build_dead_letter_producer,
    consume_one,
    report_lag,
)
from app.engagement.constants import (
    HEADER_ERROR,
    HEADER_SOURCE,
    POST_EVENTS_DLQ_TOPIC,
    POST_EVENTS_PARTITIONS,
    POST_EVENTS_TOPIC,
)
from app.engagement.models import PostTrending
from app.engagement.schema import PostEvent, PostEventType
from app.engagement.topics import ensure_topics
from app.posts.models import PostModel

pytestmark = pytest.mark.kafka

DEADLINE_SECONDS = 60


@pytest.fixture()
def publishing(bootstrap_servers):
    """The API's real producer, pointed at the test broker."""
    real = producer.build_producer(bootstrap_servers)
    producer.start(real)
    yield real
    producer.stop()


@pytest.fixture()
def dlq(bootstrap_servers):
    return build_dead_letter_producer(bootstrap_servers)


def flushed(real: Producer) -> None:
    assert real.flush(10) == 0, "Kafka acknowledged every event"


def drain(consumer: Consumer, sessions, dlq: Producer) -> list[Outcome]:
    """Run the aggregator's step until the group has every partition and no lag."""
    outcomes: list[Outcome] = []
    stop = threading.Event()
    deadline = time.monotonic() + DEADLINE_SECONDS
    while True:
        assert time.monotonic() < deadline, f"still behind after {len(outcomes)} events"
        outcome = consume_one(consumer, sessions, dlq, stop)
        if outcome is not None:
            outcomes.append(outcome)
        elif len(consumer.assignment()) == POST_EVENTS_PARTITIONS and not report_lag(consumer):
            return outcomes


def subscribed(bootstrap_servers: str, group_id: str) -> Consumer:
    consumer = build_consumer(bootstrap_servers, group_id)
    consumer.subscribe([POST_EVENTS_TOPIC])
    return consumer


def unique_post(db_session, create_user, username: str) -> PostModel:
    """A post whose id no other test uses: the broker keeps every test's events."""
    post = PostModel(
        id=100_000 + uuid.uuid4().int % 800_000,
        text="kafka",
        post_metadata="{}",
        unix_timestamp=int(time.time()),
        user=create_user(username=username),
    )
    db_session.add(post)
    db_session.commit()
    return post


def score(db_session, post_id: int) -> float:
    db_session.expire_all()
    return db_session.get(PostTrending, post_id).score


def test_topics_exist_with_their_partitions(bootstrap_servers):
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})

    topics = admin.list_topics(timeout=10).topics

    assert len(topics[POST_EVENTS_TOPIC].partitions) == POST_EVENTS_PARTITIONS
    assert POST_EVENTS_DLQ_TOPIC in topics
    assert ensure_topics(admin) == [], "a second run creates nothing"


def test_events_become_a_score_and_offsets_are_committed(
    bootstrap_servers, publishing, sessions, db_session, dlq, group_id, create_user
):
    post = unique_post(db_session, create_user, "kafka")
    for event_type in (PostEventType.LIKED, PostEventType.REPOSTED, PostEventType.UNLIKED):
        producer.emit(event_type, post.id, 1)
    flushed(publishing)

    consumer = subscribed(bootstrap_servers, group_id)
    try:
        outcomes = drain(consumer, sessions, dlq)
    finally:
        consumer.close()

    assert outcomes.count(Outcome.APPLIED) >= 3
    assert score(db_session, post.id) == pytest.approx(3.0, abs=0.01)


def test_one_posts_events_share_a_partition_in_order(bootstrap_servers, publishing, group_id):
    post_id = 900_000 + uuid.uuid4().int % 100_000
    sent = [PostEventType.LIKED, PostEventType.UNLIKED, PostEventType.LIKED]
    for event_type in sent:
        producer.emit(event_type, post_id, 1)
    flushed(publishing)

    consumer = subscribed(bootstrap_servers, group_id)
    seen: list[tuple[int, PostEventType]] = []
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        while len(seen) < len(sent):
            assert time.monotonic() < deadline
            message = consumer.poll(1.0)
            if message is None or message.error() or message.key() != str(post_id).encode():
                continue
            seen.append((message.partition(), PostEvent.model_validate_json(message.value()).type))
    finally:
        consumer.close()

    assert len({partition for partition, _ in seen}) == 1
    assert [event_type for _, event_type in seen] == sent


def test_a_restarted_consumer_resumes_and_a_new_group_replays_without_double_counting(
    bootstrap_servers, publishing, sessions, db_session, dlq, group_id, create_user
):
    post = unique_post(db_session, create_user, "replay")
    producer.emit(PostEventType.SAVED, post.id, 1)
    flushed(publishing)
    first = subscribed(bootstrap_servers, group_id)
    try:
        drain(first, sessions, dlq)
    finally:
        first.close()

    producer.emit(PostEventType.SAVED, post.id, 2)
    flushed(publishing)
    restarted = subscribed(bootstrap_servers, group_id)
    try:
        resumed = drain(restarted, sessions, dlq)
    finally:
        restarted.close()
    after_both = score(db_session, post.id)

    replay = subscribed(bootstrap_servers, f"{group_id}-replay")
    try:
        replayed = drain(replay, sessions, dlq)
    finally:
        replay.close()

    assert resumed == [Outcome.APPLIED], "the same group starts after its committed offset"
    assert after_both == pytest.approx(4.0, abs=0.01)
    assert Outcome.APPLIED not in replayed, "a new group re-reads everything, applies nothing"
    assert score(db_session, post.id) == after_both


def test_an_unparseable_event_lands_in_the_dead_letter_topic(
    bootstrap_servers, sessions, dlq, group_id
):
    marker = uuid.uuid4().hex.encode()
    raw = Producer({"bootstrap.servers": bootstrap_servers})
    raw.produce(POST_EVENTS_TOPIC, value=b"not json " + marker, key=marker)
    flushed(raw)
    consumer = subscribed(bootstrap_servers, group_id)
    try:
        assert Outcome.DEAD_LETTERED in drain(consumer, sessions, dlq)
    finally:
        consumer.close()

    reader = Consumer(
        {"bootstrap.servers": bootstrap_servers, "group.id": f"{group_id}-dlq",
         "auto.offset.reset": "earliest"}
    )  # fmt: skip
    reader.subscribe([POST_EVENTS_DLQ_TOPIC])
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        while True:
            assert time.monotonic() < deadline, "the dead letter never arrived"
            dead = reader.poll(1.0)
            if dead is not None and not dead.error() and dead.key() == marker:
                break
    finally:
        reader.close()

    headers = {key: value.decode() for key, value in dead.headers()}
    assert dead.value() == b"not json " + marker
    assert headers[HEADER_SOURCE].startswith(f"{POST_EVENTS_TOPIC}/")
    assert "validation error" in headers[HEADER_ERROR]


def test_a_new_group_is_behind_by_everything_retained(bootstrap_servers, publishing, group_id):
    producer.emit(PostEventType.LIKED, 1, 1)
    flushed(publishing)
    consumer = subscribed(bootstrap_servers, group_id)
    try:
        deadline = time.monotonic() + DEADLINE_SECONDS
        while len(consumer.assignment()) < POST_EVENTS_PARTITIONS:
            assert time.monotonic() < deadline
            consumer.poll(0.5)
        consumer.pause(consumer.assignment())  # read nothing: just measure
        committed = consumer.committed(consumer.assignment(), timeout=10)

        assert all(tp.offset == NO_OFFSET for tp in committed)
        assert report_lag(consumer) >= 1
    finally:
        consumer.close()
