"""orchestration/dags/engagement_daily.py, loaded by Airflow itself.

Run inside the Airflow image (orchestration/check.sh): Airflow isn't a
dependency of the app, and its DagBag is what the scheduler would use.
"""

import datetime
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag

DAGS = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    # Examples are off in the environment (check.sh: AIRFLOW__CORE__LOAD_EXAMPLES).
    return DagBag(dag_folder=str(DAGS))


@pytest.fixture(scope="module")
def dag(dagbag):
    return dagbag.get_dag("engagement_daily")


def test_every_dag_imports(dagbag):
    assert dagbag.import_errors == {}
    assert set(dagbag.dag_ids) == {"engagement_daily"}


def test_the_snapshot_runs_before_the_quality_gate(dag):
    assert [task.task_id for task in dag.topological_sort()] == ["snapshot", "check_counter_drift"]
    assert dag.get_task("check_counter_drift").upstream_task_ids == {"snapshot"}


def test_daily_without_catchup(dag):
    """Catching up would snapshot old dates with today's totals."""
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_the_job_retries_and_the_gate_does_not(dag):
    snapshot, gate = dag.get_task("snapshot"), dag.get_task("check_counter_drift")
    assert snapshot.retries == 2
    assert snapshot.execution_timeout == datetime.timedelta(minutes=30)
    assert gate.retries == 0, "the same data gives the same answer"


def test_both_tasks_work_on_the_runs_date(dag):
    """run_after, which every run has; a manual run in Airflow 3 has no ds."""
    for task in dag.tasks:
        assert "--date {{ dag_run.run_after.strftime('%Y-%m-%d') }}" in task.bash_command
        assert "--output /opt/airflow/lake" in task.bash_command
        assert "ds" not in task.bash_command.replace("dag_run", "")
        assert "logical_date" not in task.bash_command


def test_the_database_comes_from_the_connection_not_the_file(dag):
    env = dag.get_task("snapshot").env
    assert env["DB_PASSWORD"] == "{{ conn.radshift_db.password }}"
    assert all("conn.radshift_db" in value for value in env.values())
