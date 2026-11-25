"""Names, paths and pins for the Spark jobs (analytics/)."""

from pathlib import Path

APP_NAME = "rad-shift-engagement-daily"

# The Postgres JDBC driver Spark reads the database with. Downloaded once
# into the cache and checked against this hash, not fetched by Spark's
# --packages at run time (which trusts whatever Maven Central serves).
# 42.7.14 was published 2026-10-07; bump both together.
JDBC_DRIVER_VERSION = "42.7.14"
JDBC_DRIVER_URL = (
    "https://repo1.maven.org/maven2/org/postgresql/postgresql/"
    f"{JDBC_DRIVER_VERSION}/postgresql-{JDBC_DRIVER_VERSION}.jar"
)
# Computed from the download, which matched Maven Central's published SHA-1.
JDBC_DRIVER_SHA256 = "73914527305a40cce504b0d3d90b23caf565136912d607ae8ae7c5895512332c"
JDBC_DRIVER_CLASS = "org.postgresql.Driver"
DRIVER_CACHE_DIR = Path.home() / ".cache" / "radshift-spark"
DOWNLOAD_TIMEOUT_SECONDS = 60

# Rows per round trip from Postgres (the driver's default fetches them all).
JDBC_FETCH_SIZE = 10_000
# Parallel reads of the posts table, split on id ranges.
POSTS_READ_PARTITIONS = 4

# Where the Parquet goes: a folder here, or s3a://bucket/prefix with the
# hadoop-aws connector (analytics/README.md). gitignored.
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "lake"

# Datasets written, one folder each under the output.
POST_SNAPSHOT = "post_engagement_snapshot"  # per post, per snapshot date
AUTHOR_DAILY = "author_daily"  # per author, per snapshot date
ACTIVITY_DAILY = "activity_daily"  # per calendar day: posts, reposts, shares
COUNTER_DRIFT = "counter_drift"  # posts whose stored counters disagree with the rows
SNAPSHOT_PARTITION = "snapshot_date"
EVENT_PARTITION = "event_date"

# Engagement kinds: each is also the posts column holding its stored
# counter. The table with one row per engagement, its post column, and its
# timestamp column (None: the table has none, so it can't be dated).
ENGAGEMENT_SOURCES: dict[str, tuple[str, str, str | None]] = {
    "likes": ("post_like", "post_id", None),
    "laughs": ("post_laughs", "post_id", None),
    "saves": ("post_saves", "post_id", None),
    "shares": ("post_shares", "post_id", "timestamp"),
    "reposts": ("reposts", "original_post_id", "unix_timestamp"),
}

# A snapshot records the totals as they are when it runs, so it can only be
# taken for today, or yesterday (a daily run for yesterday's interval runs
# just after midnight). An older date would file today's totals under it.
MAX_SNAPSHOT_LAG_DAYS = 1
