# Analytics: the daily engagement job (Spark)

Roadmap item 31. A batch job, separate from the API, that reads rad-shift's Postgres with
Apache Spark and writes Parquet. It runs locally for free: Spark in local mode on this
machine, with the output in `data/lake/` (gitignored).

```sh
uv sync --group spark                                   # pyspark 4.3.0, opt-in (~450 MB); needs Java 17+
DB_HOST=127.0.0.1 DB_PORT=5433 DB_NAME=radshift DB_USER=radshift DB_PASSWORD=... \
  uv run --group spark python -m analytics.engagement   # today's snapshot
uv run --group spark python -m analytics.engagement --date 2026-11-24 --output /some/lake
uv run --group spark pytest -m spark                    # tests: local Spark + a real Postgres in Docker
```

The database settings are the API's own variables. On the first run, the pinned Postgres JDBC
driver (42.7.14) is downloaded into `~/.cache/radshift-spark/`. Every run checks it against a
SHA-256 pinned in `constants.py`; nothing is fetched by Spark's `--packages` at run time.

## What it writes

| Dataset | Grain | Partitioned by |
|---|---|---|
| `post_engagement_snapshot` | each published post, as of the snapshot date: likes, laughs, saves, shares, reposts and replies, all counted from the rows, plus a weighted score | `snapshot_date` |
| `author_daily` | each author: posts, engagement, their best post | `snapshot_date` |
| `counter_drift` | each stored counter (`posts.likes`, ...) that disagrees with its rows | `snapshot_date` |
| `activity_daily` | each calendar day: posts published, reposts, shares (all days, recomputed) | none (one small file) |

## Design, and the interview points in it

- **Extract over JDBC, in parallel.**
  - `posts` is read as 4 queries over id ranges (`partitionColumn`, `lowerBound`, `upperBound`,
    `numPartitions`), after one query for its min and max id.
  - Without that, Spark reads the whole table through a single connection and a single task.
  - `fetchsize` 10,000 stops the driver buffering every row at once.
  - Only the needed columns are selected, which is the JDBC version of column pruning.
- **A periodic snapshot fact table.**
  - Likes, laughs and saves have no timestamp, so they can't be bucketed by day.
  - The job records each post's totals every day; the day-to-day difference is the day's
    engagement.
  - Shares and reposts do have times, so `activity_daily` counts them per day.
- **Data quality as an output.**
  - The API keeps engagement twice: as rows, and as counters on `posts`.
  - `counter_drift` lists every counter that disagrees with its rows, and the job logs a
    warning when there are any.
  - A test seeds a database with mismatched counters and checks that the job finds them all.
- **Idempotent reruns.**
  - A rerun deletes its date's partition in each snapshot, then writes it.
  - Spark's `partitionOverwriteMode=dynamic` was the first version, and the Airflow drill showed
    why it's not enough:
    - it replaces only the partitions the new output contains;
    - a clean rerun has **no** drift rows, so it wrote no drift partition;
    - the earlier run's drift survived, and the quality gate kept failing on a counter that had
      been fixed.
  - A test now reruns the same day without drift and expects none.
  - Delete-then-write isn't atomic: a crash in between leaves the date missing. The gate reports
    that ("did the job run?") instead of passing. Delta Lake's `replaceWhere` does it atomically.
  - Old dates are refused (`--allow-stale` overrides). A snapshot holds today's totals, so a
    backfill would file them under an old date.
- **Small files.**
  - The first version partitioned `activity_daily` by day, which wrote 91 one-row files
    (1.1 MB) and rewrote them all every run.
  - It also wrote one day of `counter_drift` as 16 files, one per task.
  - Now: `repartition(partition column)` before `partitionBy` gives one file per date, and
    `activity_daily` is a single 16 KB file.
  - Many small files are slow to list and read: on S3 every file costs a request.
- **Transforms.** Joins of counts onto posts (left, so a post with no likes gets 0, not
  dropped), a window function to rank each author's posts (`row_number`, ties going to the
  older post), and a full outer join so a day with shares but no new posts still appears.
- **One definition of engagement.** The score uses the trending feed's weights
  (`app.engagement.schema.EVENT_WEIGHTS`), so the batch numbers and the live feed agree.

## Numbers

Measured on a laptop: Spark `local[*]` on 16 cores, with a throwaway Postgres in Docker.

- **Input:** 200,000 posts, plus 2 million engagement rows (1.2M likes, 300k laughs, 200k saves,
  200k reposts, 100k shares).
- **Run time:** 20 s end to end, including JVM startup and four writes.
- **Output:** about 4 MB of Parquet.
- **Data-quality check:** it flagged 438,321 drifted counters. The test data had deliberately
  synced only `likes`.

## S3, Databricks, and what's left

- **Writing to S3.** The roadmap's version writes the Parquet to S3. It's left out for now:
  - it needs the `hadoop-aws` connector and the AWS SDK bundle (about 600 MB of jars, on a disk
    that's nearly full);
  - storage and requests would cost fractions of a cent.

  To add it: `--output s3a://radshift-bucket/lake`, those jars in `spark.jars`, credentials
  from the default AWS chain, and the S3A "magic" committer, so tasks don't commit by renaming
  objects (S3 has no real rename).
- **Databricks (item 32)** would run the same transform in a notebook, write the tables as Delta
  instead of Parquet (ACID, time travel, `MERGE`), and read from cloud storage instead of JDBC.
- **Airflow (item 34)** runs it daily, followed by the `analytics.quality` gate
  (`orchestration/README.md`).
