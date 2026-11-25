"""analytics/quality.py: the counter-drift gate, on Parquet the job wrote."""

import datetime

import pytest

from analytics.engagement import Sources, load, transform
from analytics.quality import MissingSnapshotError, drifted
from tests.analytics.test_engagement import DAY, post, sources

pytestmark = pytest.mark.spark


def written(spark, tmp_path, data: Sources, day: datetime.date = DAY) -> str:
    load(transform(data, day), str(tmp_path), day)
    return str(tmp_path)


def test_counts_drift_per_counter_on_that_day(spark, tmp_path):
    data = sources(spark, [post(1, likes=3, saves=1), post(2, likes=1)], likes=[(1, None)])
    root = written(spark, tmp_path, data)

    assert drifted(spark, root, DAY) == {"likes": 2, "saves": 1}


def test_a_clean_day_has_no_drift(spark, tmp_path):
    root = written(spark, tmp_path, sources(spark, [post(1, likes=1)], likes=[(1, None)]))

    assert drifted(spark, root, DAY) == {}


def test_a_rerun_without_drift_clears_the_days_earlier_drift(spark, tmp_path):
    """Found in the Airflow drill: an empty result wrote no partition, so the old one stayed."""
    written(spark, tmp_path, sources(spark, [post(1, likes=7)]))
    root = written(spark, tmp_path, sources(spark, [post(1)]))

    assert drifted(spark, root, DAY) == {}


def test_only_the_asked_day_counts(spark, tmp_path):
    root = written(spark, tmp_path, sources(spark, [post(1, likes=5)]), DAY)
    written(spark, tmp_path, sources(spark, [post(1)]), DAY + datetime.timedelta(days=1))

    assert drifted(spark, root, DAY + datetime.timedelta(days=1)) == {}


def test_a_day_the_job_never_wrote_is_an_error_not_a_pass(spark, tmp_path):
    root = written(spark, tmp_path, sources(spark, [post(1)]))

    with pytest.raises(MissingSnapshotError, match="did the job run"):
        drifted(spark, root, DAY - datetime.timedelta(days=3))


def test_no_output_at_all_is_an_error(spark, tmp_path):
    with pytest.raises(MissingSnapshotError):
        drifted(spark, str(tmp_path / "empty"), DAY)
