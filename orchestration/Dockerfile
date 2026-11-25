# Airflow with the Spark job (roadmap item 34): the official image plus a
# JRE, pyspark and the few files analytics/ imports.
#
#   docker compose -f compose.airflow.yaml up -d --build      (from the repo root)
#
# Built from the repository root (the job's code lives there).

# Pinned by digest: apache/airflow 3.4.0 (Python 3.12), pushed 2026-11-06.
# It is a Docker Hardened Images build on Debian 13.
FROM apache/airflow:3.4.0-python3.12@sha256:818f94affc5bd7ce0be0cc04f2ace09aa8382e65190a73a08881229ff32700cb AS runtime

# Spark runs on the JVM. Debian 13 ships 21, which Spark 4 supports.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*
USER airflow

# Airflow's constraints file pins every dependency it was tested with; pip
# keeps Airflow itself at its version while adding pyspark (not in the file).
ARG AIRFLOW_VERSION=3.4.0
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" "pyspark==4.3.0" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt"

# The job and only what it imports from the app (the engagement weights):
# an explicit list, so nothing else of the API ends up here.
WORKDIR /opt/radshift
COPY analytics ./analytics
COPY app/__init__.py ./app/__init__.py
COPY app/common/__init__.py app/common/schema.py ./app/common/
COPY app/engagement/__init__.py app/engagement/schema.py ./app/engagement/
ENV PYTHONPATH=/opt/radshift
# The pinned JDBC driver, downloaded and checked against its SHA-256 now,
# so a task never fetches anything.
RUN python -c "from analytics.engagement import jdbc_driver; print(jdbc_driver())"
WORKDIR /opt/airflow
# Made here, owned by airflow: a new named volume mounted on it copies this
# ownership (on a missing path it would be root's, and unwritable).
RUN mkdir -p /opt/airflow/lake

# The DAG tests (orchestration/check.sh): the runtime plus pytest.
FROM runtime AS test
RUN pip install --no-cache-dir "pytest==9.2.0"
