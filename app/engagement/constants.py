"""Names and limits for post events over Kafka (app/engagement/, roadmap item 29b).

The API publishes one event per engagement (post created, liked, reposted,
...) to the post-events topic. The engagement aggregator, a separate process
with its own consumer group, turns them into a time-decayed trending score
per post (GET /posts/trending). Kafka runs in Docker (compose.yaml); it is
free software, and nothing here uses Amazon MSK or a paid cloud Kafka.
"""

# Where the brokers are, e.g. "kafka:9092". Unset: the API publishes nothing
# and the trending feed stays empty; every request works the same.
KAFKA_BOOTSTRAP_SERVERS_ENV_VAR = "KAFKA_BOOTSTRAP_SERVERS"

# Topics. The key is the post id, so every event for one post lands on the
# same partition and is consumed in the order it was produced.
POST_EVENTS_TOPIC = "post-events"
# Messages the aggregator can't parse, with the error in a header; inspect,
# fix the consumer and replay them by producing them back to POST_EVENTS_TOPIC.
POST_EVENTS_DLQ_TOPIC = "post-events-dlq"
# Three partitions: up to three aggregator instances can share the work.
POST_EVENTS_PARTITIONS = 3
DLQ_PARTITIONS = 1
# One broker locally, so one copy. A real cluster uses 3 and min.insync.replicas 2.
REPLICATION_FACTOR = 1
DAY_MS = 24 * 3600 * 1000
# A week of history to replay from (a new consumer group, or after a bug fix).
POST_EVENTS_RETENTION_MS = 7 * DAY_MS
DLQ_RETENTION_MS = 14 * DAY_MS
ADMIN_TIMEOUT_SECONDS = 15

# Producer (the API). Idempotence (which implies acks=all) stops a retried
# send from writing a duplicate or reordering a partition. The queue is
# bounded: with Kafka down, the API keeps ~10,000 events in memory for 30 s
# each and then drops (and counts) them instead of growing without limit.
PRODUCER_CLIENT_ID = "rad-shift-api"
PRODUCER_CONFIG: dict[str, str | int | bool] = {
    "enable.idempotence": True,
    "acks": "all",
    "linger.ms": 5,
    "message.timeout.ms": 30_000,
    "queue.buffering.max.messages": 10_000,
}
# Shutdown waits this long for queued events (Docker kills 10 s after stop).
FLUSH_TIMEOUT_SECONDS = 5

# Consumer (the aggregator). Offsets are committed by hand, after the score
# is in the database: a crash in between replays the event, and the
# processed-events table makes the replay a no-op (at-least-once delivery,
# effectively-once effect).
CONSUMER_GROUP = "engagement-aggregator"
CONSUMER_CLIENT_ID = "engagement-aggregator"
CONSUMER_CONFIG: dict[str, str | int | bool] = {
    "enable.auto.commit": False,
    # A new group starts from the oldest retained event: the score is rebuilt.
    "auto.offset.reset": "earliest",
}
POLL_TIMEOUT_SECONDS = 1.0
# After a database error, wait and re-read the same message.
ERROR_BACKOFF_SECONDS = 5
DLQ_FLUSH_TIMEOUT_SECONDS = 10
WATERMARK_TIMEOUT_SECONDS = 5
LAG_REPORT_INTERVAL_SECONDS = 15
# Processed event ids are kept a day longer than the topic keeps events,
# so any event that can still be replayed is still recognised.
PRUNE_INTERVAL_SECONDS = 3600
PROCESSED_EVENT_RETENTION_SECONDS = POST_EVENTS_RETENTION_MS // 1000 + 24 * 3600
# Prometheus scrapes the aggregator here (observability/prometheus/prometheus.yml).
AGGREGATOR_METRICS_PORT = 9102

# Message headers on a dead-lettered event.
HEADER_ERROR = "error"
HEADER_SOURCE = "source"  # topic/partition/offset it came from
MAX_ERROR_HEADER_CHARS = 500

# Trending: each event adds its weight to the post's score, and the score
# halves every 6 hours, so a post trends on what happened recently, unlike
# /posts/algo, which ranks lifetime counts. An undo (unlike) subtracts.
HALF_LIFE_SECONDS = 6 * 3600
# Posts untouched for longer have decayed below a 1/256 of their score.
TRENDING_WINDOW_SECONDS = 8 * HALF_LIFE_SECONDS
# Candidates ranked per request, newest activity first.
TRENDING_CANDIDATES = 500
# Below this (a single like, two days old), a post no longer trends.
TRENDING_MIN_SCORE = 0.05

LOG_EVENT_PUBLISH_DROPPED = "engagement.publish.dropped"
LOG_EVENT_DELIVERY_FAILED = "engagement.delivery.failed"
LOG_EVENT_UNDELIVERED_AT_STOP = "engagement.publish.undelivered_at_stop"
LOG_EVENT_TOPIC_CREATED = "engagement.topic.created"
LOG_EVENT_APPLIED = "engagement.event.applied"
LOG_EVENT_NO_POST = "engagement.event.no_post"
LOG_EVENT_DEAD_LETTERED = "engagement.event.dead_lettered"
LOG_EVENT_DB_FAILED = "engagement.event.db_failed"
LOG_EVENT_CONSUME_ERROR = "engagement.consume.error"
LOG_EVENT_COMMIT_FAILED = "engagement.commit.failed"
LOG_EVENT_LAG_FAILED = "engagement.lag.failed"
LOG_EVENT_PRUNE_FAILED = "engagement.prune.failed"
LOG_EVENT_PRUNED = "engagement.processed.pruned"
LOG_EVENT_STARTED = "engagement.aggregator.started"
LOG_EVENT_STOPPED = "engagement.aggregator.stopped"
