"""Daily engagement snapshot (analytics/engagement.py), then a data-quality gate.

1. snapshot: the Spark job reads rad-shift's Postgres and writes today's
   Parquet into the lake. Retried twice with backoff: a database restart or
   a slow JVM start shouldn't page anyone.
2. check_counter_drift: fails when any stored counter disagrees with its
   rows. Not retried: the same data gives the same answer, so a failure here
   is news.

No catchup and no backfill of the snapshot: it records the totals as they
are now, so a run for an old date would file today's numbers under it. The
job refuses such a date (analytics/README.md).

The database comes from the Airflow connection radshift_db (set in
compose.airflow.yaml as AIRFLOW_CONN_RADSHIFT_DB), not from this file.
"""

import datetime

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

DAG_ID = "engagement_daily"
# The run's date. Not {{ ds }}: in Airflow 3 a manually triggered run has no
# logical date, so ds is undefined and the template fails (it did, on the
# first manual run). Every run has run_after: midnight for the daily
# schedule, the moment of the trigger for a manual run.
RUN_DATE = "{{ dag_run.run_after.strftime('%Y-%m-%d') }}"
LAKE = "/opt/airflow/lake"
JOB_DIR = "/opt/radshift"
# The job reads the API's own settings; rendered from the connection at run
# time. Airflow masks the password in logs and the rendered-fields view.
DB_ENV = {
    "DB_HOST": "{{ conn.radshift_db.host }}",
    "DB_PORT": "{{ conn.radshift_db.port }}",
    "DB_NAME": "{{ conn.radshift_db.schema }}",
    "DB_USER": "{{ conn.radshift_db.login }}",
    "DB_PASSWORD": "{{ conn.radshift_db.password }}",
}

with DAG(
    dag_id=DAG_ID,
    schedule="@daily",
    start_date=pendulum.datetime(2026, 11, 24, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": datetime.timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "execution_timeout": datetime.timedelta(minutes=30),
    },
    tags=["analytics", "spark"],
    doc_md=__doc__,
):
    snapshot = BashOperator(
        task_id="snapshot",
        bash_command=f"python -m analytics.engagement --date {RUN_DATE} --output {LAKE}",
        env=DB_ENV,
        append_env=True,
        cwd=JOB_DIR,
    )
    check_counter_drift = BashOperator(
        task_id="check_counter_drift",
        bash_command=f"python -m analytics.quality --date {RUN_DATE} --output {LAKE} --max-drift 0",
        cwd=JOB_DIR,
        retries=0,
    )

    snapshot >> check_counter_drift
