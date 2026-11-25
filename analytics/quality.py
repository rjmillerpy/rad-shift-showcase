"""Data-quality gate on a snapshot: fail when stored counters have drifted.

    uv run --group spark python -m analytics.quality --date 2026-11-25 [--output data/lake] [--max-drift 0]

Exits 1 when the date's counter_drift has more rows than --max-drift, so a
scheduler marks the run failed and alerts, instead of the numbers quietly
disagreeing (orchestration/, item 34, runs it after the snapshot).
"""

import argparse
import datetime
import logging
import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.utils import AnalysisException

from analytics.constants import (
    APP_NAME,
    COUNTER_DRIFT,
    DEFAULT_OUTPUT,
    POST_SNAPSHOT,
    SNAPSHOT_PARTITION,
)

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_DRIFTED = 1


class MissingSnapshotError(Exception):
    """The job hasn't written this date (it didn't run, or ran elsewhere)."""


def _on(spark: SparkSession, root: str, dataset: str, snapshot_date: datetime.date) -> DataFrame:
    path = f"{root.rstrip('/')}/{dataset}"
    try:
        frame = spark.read.parquet(path)
    except AnalysisException as error:
        raise MissingSnapshotError(f"no {dataset} dataset at {path}") from error
    return frame.filter(F.col(SNAPSHOT_PARTITION) == F.lit(snapshot_date))


def drifted(spark: SparkSession, root: str, snapshot_date: datetime.date) -> dict[str, int]:
    """Drifted counters on that date, per counter (empty: none drifted).

    A day without drift writes no counter_drift rows, which looks the same as
    a day the job never ran; the post snapshot tells them apart.
    """
    if _on(spark, root, POST_SNAPSHOT, snapshot_date).isEmpty():
        raise MissingSnapshotError(f"no {POST_SNAPSHOT} for {snapshot_date}: did the job run?")
    try:
        drift = _on(spark, root, COUNTER_DRIFT, snapshot_date)
    except MissingSnapshotError:
        return {}  # no drift on any day yet: Spark wrote no files at all
    return {row["counter"]: row["count"] for row in drift.groupBy("counter").count().collect()}


def main(
    argv: list[str] | None = None,
) -> None:  # pragma: no cover - process wiring; drifted() is tested
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=datetime.date.fromisoformat, required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-drift", type=int, default=0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    spark = SparkSession.builder.appName(f"{APP_NAME}-quality").master("local[1]").getOrCreate()
    try:
        counts = drifted(spark, args.output, args.date)
    finally:
        spark.stop()
    total = sum(counts.values())
    logger.info("counter drift on %s: %d %s", args.date, total, counts)
    sys.exit(EXIT_DRIFTED if total > args.max_drift else EXIT_OK)


if __name__ == "__main__":  # pragma: no cover
    main()
