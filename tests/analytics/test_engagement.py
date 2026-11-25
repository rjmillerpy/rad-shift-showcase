"""analytics/engagement.py: the daily engagement job (roadmap item 31).

Transform tests build small DataFrames by hand; TestTheWholeJob seeds a
real Postgres through the app's models and reads the Parquet it writes.
"""

import datetime
import hashlib
import time

import pytest
from sqlalchemy.orm import Session

from analytics.constants import (
    ACTIVITY_DAILY,
    AUTHOR_DAILY,
    COUNTER_DRIFT,
    JDBC_DRIVER_VERSION,
    POST_SNAPSHOT,
)
from analytics.engagement import (
    POST_COLUMNS,
    WEIGHTS,
    DriverChecksumError,
    Sources,
    StaleSnapshotError,
    check_snapshot_date,
    jdbc_driver,
    jdbc_options,
    run,
    transform,
)
from app.auth.models import User
from app.posts.models import PostLike, PostModel, PostSave, PostShare, Repost

pytestmark = pytest.mark.spark

DAY = datetime.date(2026, 11, 25)
NOON = int(datetime.datetime(2026, 11, 25, 12, tzinfo=datetime.UTC).timestamp())
ONE_DAY = 86_400
POSTS_SCHEMA = (
    "id INT, user_id INT, unix_timestamp INT, is_draft BOOLEAN, is_reply BOOLEAN, "
    "parent_post_id INT, likes INT, laughs INT, saves INT, shares INT, reposts INT"
)
ENGAGEMENT_SCHEMA = "post_id INT, at BIGINT"


def post(id, user_id=1, at=NOON, draft=False, reply_to=None, **stored):
    counters = {kind: stored.get(kind, 0) for kind in WEIGHTS}
    return (id, user_id, at, draft, reply_to is not None, reply_to, counters["likes"],
            counters["laughs"], counters["saves"], counters["shares"], counters["reposts"])  # fmt: skip


def sources(spark, posts, **engagements) -> Sources:
    frames = {
        kind: spark.createDataFrame(engagements.get(kind, []), ENGAGEMENT_SCHEMA)
        for kind in WEIGHTS
    }
    return Sources(posts=spark.createDataFrame(posts, POSTS_SCHEMA), engagements=frames)


def rows(frame, key="post_id") -> dict:
    return {row[key]: row.asDict() for row in frame.collect()}


def test_the_posts_schema_here_is_the_jobs():
    assert [column.split()[0] for column in POSTS_SCHEMA.split(", ")] == POST_COLUMNS


class TestPostSnapshot:
    def test_counts_each_kind_from_its_rows(self, spark):
        data = sources(spark, [post(1), post(2)],
                       likes=[(1, None), (1, None), (2, None)], reposts=[(1, NOON)])  # fmt: skip

        snapshot = rows(transform(data, DAY).post_snapshot)

        assert (snapshot[1]["likes"], snapshot[1]["reposts"], snapshot[1]["saves"]) == (2, 1, 0)
        assert snapshot[2]["likes"] == 1

    def test_the_score_uses_the_trending_weights(self, spark):
        data = sources(spark, [post(1)], likes=[(1, None)], saves=[(1, None)], shares=[(1, NOON)])

        score = rows(transform(data, DAY).post_snapshot)[1]["engagement_score"]

        assert score == WEIGHTS["likes"] + WEIGHTS["saves"] + WEIGHTS["shares"]

    def test_only_published_top_level_posts_with_their_replies_counted(self, spark):
        data = sources(spark, [post(1), post(2, draft=True), post(3, reply_to=1),
                               post(4, reply_to=1, draft=True)])  # fmt: skip

        snapshot = rows(transform(data, DAY).post_snapshot)

        assert set(snapshot) == {1}
        assert snapshot[1]["replies"] == 1, "a draft reply isn't a reply yet"

    def test_dates_and_age(self, spark):
        data = sources(spark, [post(1, at=NOON - 3 * ONE_DAY)])

        snapshot = rows(transform(data, DAY).post_snapshot)[1]

        assert snapshot["created_date"] == datetime.date(2026, 11, 22)
        assert snapshot["age_days"] == 3
        assert snapshot["snapshot_date"] == DAY


class TestAuthorDaily:
    def test_totals_and_the_best_post(self, spark):
        data = sources(spark, [post(1, user_id=7), post(2, user_id=7), post(3, user_id=8)],
                       likes=[(2, None), (2, None), (1, None), (3, None)])  # fmt: skip

        authors = rows(transform(data, DAY).author_daily, key="author_id")

        assert (authors[7]["posts"], authors[7]["likes"], authors[7]["best_post_id"]) == (2, 3, 2)
        assert authors[8]["best_post_id"] == 3

    def test_a_tie_goes_to_the_older_post(self, spark):
        data = sources(spark, [post(5, user_id=7), post(4, user_id=7)])

        assert rows(transform(data, DAY).author_daily, key="author_id")[7]["best_post_id"] == 4


class TestActivityDaily:
    def test_posts_reposts_and_shares_per_day(self, spark):
        yesterday = NOON - ONE_DAY
        data = sources(spark, [post(1, at=yesterday), post(2), post(3)],
                       reposts=[(1, yesterday), (1, NOON)],
                       shares=[(2, NOON - 3 * ONE_DAY)])  # fmt: skip

        days = rows(transform(data, DAY).activity_daily, key="event_date")

        assert days[DAY] | {} == {
            "event_date": DAY,
            "posts_published": 2,
            "shares": 0,
            "reposts": 1,
        }
        assert days[DAY - datetime.timedelta(days=1)]["reposts"] == 1
        assert days[datetime.date(2026, 11, 22)]["posts_published"] == 0, (
            "a day with only a share still appears"
        )


class TestCounterDrift:
    def test_reports_only_counters_that_disagree(self, spark):
        data = sources(spark, [post(1, likes=2), post(2, likes=5, saves=1)],
                       likes=[(1, None), (1, None), (2, None)], saves=[(2, None)])  # fmt: skip

        drift = [row.asDict() for row in transform(data, DAY).counter_drift.collect()]

        assert drift == [{"post_id": 2, "counter": "likes", "stored": 5, "counted": 1,
                          "snapshot_date": DAY}]  # fmt: skip


class TestSnapshotDate:
    """The snapshot holds today's totals, so only today or yesterday is honest."""

    def test_today_and_yesterday_are_fine(self):
        check_snapshot_date(DAY, today=DAY)
        check_snapshot_date(DAY - datetime.timedelta(days=1), today=DAY)

    def test_an_older_date_is_refused(self):
        with pytest.raises(StaleSnapshotError, match="--allow-stale"):
            check_snapshot_date(DAY - datetime.timedelta(days=2), today=DAY)

    def test_a_future_date_is_refused(self):
        with pytest.raises(StaleSnapshotError, match="future"):
            check_snapshot_date(DAY + datetime.timedelta(days=1), today=DAY)


class TestJdbcDriver:
    def test_a_cached_driver_is_used_without_downloading(self, tmp_path):
        jar = tmp_path / f"postgresql-{JDBC_DRIVER_VERSION}.jar"
        jar.write_bytes(b"driver")

        found = jdbc_driver(tmp_path, url="file:///nonexistent",
                            sha256=hashlib.sha256(b"driver").hexdigest())  # fmt: skip

        assert found == jar

    def test_a_download_with_the_wrong_hash_is_refused_and_removed(self, tmp_path):
        source = tmp_path / "served.jar"
        source.write_bytes(b"tampered")
        cache = tmp_path / "cache"

        with pytest.raises(DriverChecksumError, match="expected"):
            jdbc_driver(cache, url=source.as_uri(), sha256="0" * 64)

        assert list(cache.iterdir()) == []

    def test_options_come_from_the_apis_settings(self):
        options = jdbc_options({"DB_HOST": "db", "DB_NAME": "radshift", "DB_USER": "u",
                                "DB_PASSWORD": "p"})  # fmt: skip

        # The URL names the host, port and database; credentials stay separate.
        assert options["url"].startswith("jdbc:postgresql:")
        assert options["url"].endswith("//db:5432/radshift")
        assert (options["user"], options["password"]) == ("u", "p")


class TestTheWholeJob:
    """Postgres -> Spark -> Parquet, then read back with Spark."""

    @pytest.fixture()
    def seeded(self, pg_engine):
        with Session(pg_engine) as db:
            for table in (PostLike, PostSave, PostShare, Repost, PostModel, User):
                db.query(table).delete()
            author = User(username="author", email="a@example.com", password_hash="x")
            fan = User(username="fan", email="f@example.com", password_hash="x")
            db.add_all([author, fan])
            db.flush()
            posts = [PostModel(text=f"p{i}", post_metadata="{}", user_id=author.id,
                               unix_timestamp=NOON, likes=1) for i in range(6)]  # fmt: skip
            db.add_all(posts)
            db.flush()
            db.add_all([PostLike(user_id=fan.id, post_id=p.id) for p in posts[:5]])
            db.add_all([Repost(user_id=fan.id, original_post_id=posts[0].id, unix_timestamp=NOON),
                        PostSave(user_id=fan.id, post_id=posts[0].id),
                        PostShare(user_id=fan.id, post_id=posts[1].id, timestamp=int(time.time()))])  # fmt: skip
            db.commit()
            return {"author": author.id, "first": posts[0].id, "unliked": posts[5].id}

    def test_writes_every_dataset_and_reads_back(self, spark, postgres, seeded, tmp_path, caplog):
        with caplog.at_level("WARNING", logger="analytics.engagement"):
            run(spark, jdbc_options(postgres), str(tmp_path), DAY)

        snapshot = rows(spark.read.parquet(str(tmp_path / POST_SNAPSHOT)))
        author = rows(spark.read.parquet(str(tmp_path / AUTHOR_DAILY)), key="author_id")
        drift = spark.read.parquet(str(tmp_path / COUNTER_DRIFT)).collect()

        assert len(snapshot) == 6
        assert snapshot[seeded["first"]]["engagement_score"] == (
            WEIGHTS["likes"] + WEIGHTS["reposts"] + WEIGHTS["saves"]
        )
        assert author[seeded["author"]]["best_post_id"] == seeded["first"]
        activity = rows(spark.read.parquet(str(tmp_path / ACTIVITY_DAILY)), key="event_date")
        assert activity[DAY]["posts_published"] == 6
        # posts.likes says 1 everywhere; the sixth post has no like row, and
        # the first post's stored reposts/saves (0) disagree with its rows.
        assert {(row.post_id, row.counter) for row in drift} == {
            (seeded["unliked"], "likes"),
            (seeded["first"], "reposts"),
            (seeded["first"], "saves"),
            (seeded["first"] + 1, "shares"),
        }
        assert "4 stored engagement counters disagree" in caplog.text

    def test_a_rerun_replaces_its_day_and_keeps_the_others(self, spark, postgres, seeded, tmp_path):
        options, root = jdbc_options(postgres), str(tmp_path)
        run(spark, options, root, DAY - datetime.timedelta(days=1))
        run(spark, options, root, DAY)
        run(spark, options, root, DAY)

        snapshot = spark.read.parquet(str(tmp_path / POST_SNAPSHOT))
        per_day = {
            row.snapshot_date: row["count"]
            for row in snapshot.groupBy("snapshot_date").count().collect()
        }

        assert per_day == {DAY - datetime.timedelta(days=1): 6, DAY: 6}
        day = tmp_path / POST_SNAPSHOT / f"snapshot_date={DAY}"
        assert len(list(day.glob("*.parquet"))) == 1, "one file per day, not one per task"

    def test_an_empty_database_writes_empty_datasets(self, spark, postgres, pg_engine, tmp_path):
        with Session(pg_engine) as db:
            for table in (PostLike, PostSave, PostShare, Repost, PostModel):
                db.query(table).delete()
            db.commit()

        outputs = run(spark, jdbc_options(postgres), str(tmp_path), DAY)

        assert outputs.post_snapshot.count() == 0
