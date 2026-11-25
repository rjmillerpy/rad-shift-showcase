# Orchestration: Airflow runs the Spark job daily

Roadmap item 34. Airflow 3.4 runs in Docker beside the app stack, for free. Each day it runs
the engagement job (`analytics/`, item 31), then a data-quality gate.

```sh
docker compose up -d                                    # the app stack (its database)
docker compose -f compose.airflow.yaml up -d --build    # Airflow: http://localhost:8090, user admin
docker compose -f compose.airflow.yaml logs airflow | grep -i password    # generated on first start
docker compose -f compose.airflow.yaml exec airflow airflow dags trigger engagement_daily
orchestration/check.sh                                  # DAG tests, inside the Airflow image
docker compose -f compose.airflow.yaml down             # stop (add -v to drop its database and the lake)
```

| Path | What it is |
|---|---|
| `dags/engagement_daily.py` | The DAG: `snapshot` >> `check_counter_drift`, daily, no catchup |
| `Dockerfile` | `apache/airflow:3.4.0` (by digest), plus a JRE, pyspark, and only the files the job imports. The JDBC driver is fetched and checked at build time |
| `tests/` | DAG tests run against Airflow's own `DagBag` (imports, order, schedule, retries, templates) |
| `../compose.airflow.yaml` | Airflow (standalone: api-server, scheduler, DAG processor, triggerer) and its own Postgres |

Footprint: about 1.1 GB of RAM, and a 2.2 GB image.

## The DAG

- **`snapshot`:**
  - runs `python -m analytics.engagement` for the run's date;
  - retries twice with exponential backoff, because a database restart or a slow JVM start
    shouldn't page anyone;
  - times out after 30 min.
- **`check_counter_drift`:**
  - runs `python -m analytics.quality --max-drift 0`;
  - fails when any stored counter disagrees with its rows;
  - has **no retries**: the same data gives the same answer, so a failure is news.
- **No catchup, one active run:** a snapshot holds today's totals, so catching up old dates would
  file today's numbers under them. The job refuses that anyway.
- **The database is an Airflow connection** (`radshift_db`, from `AIRFLOW_CONN_RADSHIFT_DB`),
  rendered into the task's environment. Airflow masks the password in logs and in the
  rendered-template view. In production it would come from a secrets backend (AWS Secrets
  Manager) instead of an environment variable.

## Drills (2026-11-25)

- **The scheduled run succeeded:** the snapshot, then the gate, in 29 s.
- **The first manual run failed:** `'ds' is undefined`.
  - In Airflow 3, a manually triggered run has **no logical date**, so `{{ ds }}` can't render.
  - Airflow retried the template error twice, wasting the retries.
  - Fixed: the date comes from `dag_run.run_after`, which every run has, and a test checks for
    it.
  - The stuck run's last retry then succeeded, because retries run the current DAG code.
- **A drifted counter failed the gate:** with `posts.likes` set to 7 against 0 like rows, the
  snapshot succeeded, the gate failed on its first attempt with `{'likes': 1}`, and nothing
  retried.
- **The fix-and-rerun exposed a bug in the job:** the clean rerun still failed, because the
  earlier run's drift partition was never replaced (`analytics/README.md`, idempotent reruns).
  After the fix, the clean rerun passes.

## Interview points

- **Airflow 3's architecture:**
  - the API server (the UI and REST, and the task execution API that workers report to);
  - the scheduler;
  - the DAG processor (parses DAG files, separate from the scheduler since Airflow 3);
  - the triggerer (deferrable tasks);
  - the metadata database.
- **Executors:** Local (processes, as here), Celery (a worker fleet), Kubernetes (one pod per
  task).
- **DAG concepts:** DAG vs task vs task instance vs run; `run_after` and `logical_date`, and why a
  manual run lacks the latter in 3.x; idempotent tasks; retries vs alerting.
- **Data correctness:** catchup and backfills, and why a snapshot can't be backfilled; data
  quality as a task that fails the run.
- **Operations:** connections and secrets backends; templates rendered at run time; keeping heavy
  work out of the scheduler (Spark runs as the task's process, never at DAG-parse time).
- **Airflow vs Dagster:** tasks vs software-defined assets. Dagster's asset checks are the same
  idea as the drift gate.
- **On AWS:** MWAA (managed Airflow) costs about $350+ a month for the smallest environment. Step
  Functions (item 29) suits short workflows; Airflow suits data pipelines with backfills and
  dependencies between days.
