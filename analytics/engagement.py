"""The daily engagement job: Postgres -> Spark -> Parquet (roadmap item 31).

    uv run --group spark python -m analytics.engagement                 # today, into data/lake
    uv run --group spark python -m analytics.engagement --date 2026-11-25 --output /some/lake

Extract: reads posts, users' engagement rows (likes, laughs, saves, shares,
reposts) over JDBC, posts in parallel id ranges. The database settings are
the API's own (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).

Transform, into four datasets:
  post_engagement_snapshot  each published post as of the snapshot date: its
                            engagement counted from the rows, replies, and a
                            weighted score (the trending feed's weights)
  author_daily              per author: posts, engagement, their best post
  activity_daily            per calendar day: posts published, reposts, shares
                            (all days, recomputed each run)
  counter_drift             posts whose stored counters (posts.likes, ...)
                            disagree with the rows: the API keeps both, and
                            this is where they'd be seen drifting apart

Likes, laughs and saves carry no timestamp, so they can't be bucketed by
day: the snapshot records totals each day instead, and the day-to-day
difference is the day's engagement (a periodic snapshot fact table).

Load: Parquet. The snapshots are partitioned by snapshot date, and a rerun
replaces only the dates it writes (dynamic partition overwrite), so a day can
be re-run safely.
"""

import argparse
import datetime
import hashlib
import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from analytics.constants import (
    ACTIVITY_DAILY,
    APP_NAME,
    AUTHOR_DAILY,
    COUNTER_DRIFT,
    DEFAULT_OUTPUT,
    DOWNLOAD_TIMEOUT_SECONDS,
    DRIVER_CACHE_DIR,
    ENGAGEMENT_SOURCES,
    EVENT_PARTITION,
    JDBC_DRIVER_CLASS,
    JDBC_DRIVER_SHA256,
    JDBC_DRIVER_URL,
    JDBC_DRIVER_VERSION,
    JDBC_FETCH_SIZE,
    POST_SNAPSHOT,
    POSTS_READ_PARTITIONS,
    SNAPSHOT_PARTITION,
)
from app.engagement.schema import EVENT_WEIGHTS, PostEventType

logger = logging.getLogger(__name__)

# The trending feed's weight for each kind of engagement.
WEIGHTS = {
    "likes": EVENT_WEIGHTS[PostEventType.LIKED],
    "laughs": EVENT_WEIGHTS[PostEventType.LAUGHED],
    "saves": EVENT_WEIGHTS[PostEventType.SAVED],
    "shares": EVENT_WEIGHTS[PostEventType.SHARED],
    "reposts": EVENT_WEIGHTS[PostEventType.REPOSTED],
}
POST_COLUMNS = ["id", "user_id", "unix_timestamp", "is_draft", "is_reply", "parent_post_id",
                *ENGAGEMENT_SOURCES]  # fmt: skip


class DriverChecksumError(Exception):
    """The downloaded JDBC driver isn't the file that was pinned."""


@dataclass(frozen=True)
class Sources:
    posts: DataFrame
    # Engagement kind -> one row per engagement: post_id, and at (unix
    # seconds, null for kinds stored without a time).
    engagements: dict[str, DataFrame]


@dataclass(frozen=True)
class Outputs:
    post_snapshot: DataFrame
    author_daily: DataFrame
    activity_daily: DataFrame
    counter_drift: DataFrame


def jdbc_driver(cache_dir: Path = DRIVER_CACHE_DIR, url: str = JDBC_DRIVER_URL,
                sha256: str = JDBC_DRIVER_SHA256) -> Path:  # fmt: skip
    """The pinned driver jar: downloaded once, verified every time."""
    jar = cache_dir / f"postgresql-{JDBC_DRIVER_VERSION}.jar"
    if not jar.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        partial = jar.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # nosec B310 - fixed https URL
            partial.write_bytes(response.read())
        partial.rename(jar)
    digest = hashlib.sha256(jar.read_bytes()).hexdigest()
    if digest != sha256:
        jar.unlink()
        raise DriverChecksumError(f"{jar.name}: sha256 {digest}, expected {sha256}")
    return jar


def spark_session(driver_jar: Path, master: str = "local[*]") -> SparkSession:
    return (
        SparkSession.builder.appName(APP_NAME)
        .master(master)
        .config("spark.jars", str(driver_jar))
        # Rewrite only the partitions this run produces (the default,
        # "static", would delete every other day's data on overwrite).
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.session.timeZone", "UTC")
        # Small data: a few shuffle partitions, not the default 200.
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def jdbc_options(environ: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    return {
        "url": f"jdbc:postgresql://{env['DB_HOST']}:{env.get('DB_PORT', '5432')}/{env['DB_NAME']}",
        "user": env["DB_USER"],
        "password": env["DB_PASSWORD"],
        "driver": JDBC_DRIVER_CLASS,
        "fetchsize": str(JDBC_FETCH_SIZE),
    }


def _read(spark: SparkSession, options: dict[str, str], query: str, **extra: str) -> DataFrame:
    return spark.read.format("jdbc").options(**options, **extra).option("query", query).load()


def read_posts(spark: SparkSession, options: dict[str, str]) -> DataFrame:
    """Posts, read in parallel: one query per id range instead of one for everything."""
    bounds = _read(spark, options, "SELECT min(id) AS low, max(id) AS high FROM posts").first()
    columns = ", ".join(POST_COLUMNS)
    if bounds is None or bounds["low"] is None:
        return _read(spark, options, f"SELECT {columns} FROM posts")  # nosec B608 - fixed columns
    return (
        spark.read.format("jdbc")
        .options(**options)
        .option("dbtable", f"(SELECT {columns} FROM posts) AS posts")  # nosec B608 - fixed columns
        .option("partitionColumn", "id")
        .option("lowerBound", str(bounds["low"]))
        .option("upperBound", str(bounds["high"] + 1))
        .option("numPartitions", str(POSTS_READ_PARTITIONS))
        .load()
    )


def extract(spark: SparkSession, options: dict[str, str]) -> Sources:
    engagements = {
        kind: _read(spark, options,
                    f"SELECT {column} AS post_id, {at or 'NULL::bigint'} AS at FROM {table}")  # nosec B608 - fixed names
        for kind, (table, column, at) in ENGAGEMENT_SOURCES.items()
    }  # fmt: skip
    return Sources(posts=read_posts(spark, options), engagements=engagements)


def _counted(sources: Sources) -> DataFrame:
    """post_id plus one column per engagement kind, counted from the rows (0 when none)."""
    published = sources.posts.filter(~F.col("is_draft") & ~F.col("is_reply")).select(
        F.col("id").alias("post_id"),
        F.col("user_id").alias("author_id"),
        F.col("unix_timestamp"),
    )
    replies = (
        sources.posts.filter(F.col("is_reply") & ~F.col("is_draft"))
        .groupBy(F.col("parent_post_id").alias("post_id"))
        .agg(F.count("*").alias("replies"))
    )
    counted = published.join(replies, "post_id", "left")
    for kind, rows in sources.engagements.items():
        counts = rows.groupBy("post_id").agg(F.count("*").alias(kind))
        counted = counted.join(counts, "post_id", "left")
    return counted.fillna(0, subset=["replies", *sources.engagements])


def transform(sources: Sources, snapshot_date: datetime.date) -> Outputs:
    snapshot = F.lit(snapshot_date)
    created = F.to_date(F.from_unixtime(F.col("unix_timestamp")))
    score = sum((F.col(kind) * weight for kind, weight in WEIGHTS.items()), F.lit(0.0))

    post_snapshot = (
        _counted(sources)
        .withColumn("created_date", created)
        .withColumn("age_days", F.datediff(snapshot, created))
        .withColumn("engagement_score", score)
        .withColumn(SNAPSHOT_PARTITION, snapshot)
        .drop("unix_timestamp")
    )

    # Each author's best post: a window ranks their posts by score.
    best_first = Window.partitionBy("author_id").orderBy(
        F.col("engagement_score").desc(), F.col("post_id").asc()
    )
    best = (
        post_snapshot.withColumn("rank", F.row_number().over(best_first))
        .filter(F.col("rank") == 1)
        .select("author_id", F.col("post_id").alias("best_post_id"))
    )
    author_daily = (
        post_snapshot.groupBy("author_id", SNAPSHOT_PARTITION)
        .agg(
            F.count("*").alias("posts"),
            F.sum("engagement_score").alias("engagement_score"),
            *(F.sum(kind).alias(kind) for kind in [*WEIGHTS, "replies"]),
        )
        .join(best, "author_id")
    )

    activity_daily = post_snapshot.groupBy(F.col("created_date").alias(EVENT_PARTITION)).agg(
        F.count("*").alias("posts_published")
    )
    for kind, (_, _, at) in ENGAGEMENT_SOURCES.items():
        if at is None:
            continue
        per_day = (
            sources.engagements[kind]
            .groupBy(F.to_date(F.from_unixtime("at")).alias(EVENT_PARTITION))
            .agg(F.count("*").alias(kind))
        )
        activity_daily = activity_daily.join(per_day, EVENT_PARTITION, "full")
    activity_daily = activity_daily.fillna(0)

    stored = sources.posts.select(F.col("id").alias("post_id"), *(
        F.coalesce(F.col(kind), F.lit(0)).alias(f"stored_{kind}") for kind in ENGAGEMENT_SOURCES
    ))  # fmt: skip
    drift_rows = [
        post_snapshot.join(stored, "post_id")
        .filter(F.col(kind) != F.col(f"stored_{kind}"))
        .select(
            "post_id",
            F.lit(kind).alias("counter"),
            F.col(f"stored_{kind}").cast("long").alias("stored"),
            F.col(kind).cast("long").alias("counted"),
            F.col(SNAPSHOT_PARTITION),
        )
        for kind in ENGAGEMENT_SOURCES
    ]
    counter_drift = drift_rows[0]
    for rows in drift_rows[1:]:
        counter_drift = counter_drift.unionByName(rows)

    return Outputs(post_snapshot, author_daily, activity_daily, counter_drift)


def load(outputs: Outputs, root: str) -> None:
    """Parquet under root, one folder per dataset.

    The snapshots are partitioned by date, one file per date: repartitioning
    by the partition column first stops each task from writing its own small
    file into every partition (16 files for one day of drift, measured).
    activity_daily is recomputed in full each run and is small (one row a
    day), so it is a single file: partitioned by day it was 91 files of one
    row each, rewritten every run.
    """
    root = root.rstrip("/")
    snapshots = [
        (outputs.post_snapshot, POST_SNAPSHOT),
        (outputs.author_daily, AUTHOR_DAILY),
        (outputs.counter_drift, COUNTER_DRIFT),
    ]
    for frame, name in snapshots:
        (frame.repartition(SNAPSHOT_PARTITION).write.mode("overwrite")
         .partitionBy(SNAPSHOT_PARTITION).parquet(f"{root}/{name}"))  # fmt: skip
    outputs.activity_daily.coalesce(1).write.mode("overwrite").parquet(f"{root}/{ACTIVITY_DAILY}")


def run(
    spark: SparkSession, options: dict[str, str], root: str, snapshot_date: datetime.date
) -> Outputs:
    outputs = transform(extract(spark, options), snapshot_date)
    load(outputs, root)
    drifted = outputs.counter_drift.count()
    if drifted:
        logger.warning("%d stored engagement counters disagree with their rows", drifted)
    return outputs


def main(
    argv: list[str] | None = None,
) -> None:  # pragma: no cover - process wiring; run() is tested
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=datetime.date.fromisoformat,
                        default=datetime.datetime.now(datetime.UTC).date(),
                        help="snapshot date (UTC), default today")  # fmt: skip
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="folder or s3a:// URL")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    spark = spark_session(jdbc_driver())
    try:
        run(spark, jdbc_options(), args.output, args.date)
    finally:
        spark.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
