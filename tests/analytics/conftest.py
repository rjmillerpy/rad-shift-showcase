"""A local Spark session and a real Postgres for tests/analytics/ (marker spark)."""

import logging
import shutil
import socket
import subprocess  # nosec B404 - fixed docker commands, never a shell
import time
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from analytics.engagement import jdbc_driver, spark_session
from app.common.db import Base

POSTGRES_IMAGE = "postgres:16"  # compose.yaml's
READY_TIMEOUT_SECONDS = 60
PASSWORD = "analytics-test"


@pytest.fixture(scope="session")
def spark():
    if shutil.which("java") is None:
        pytest.skip("needs Java 17+")
    session = spark_session(jdbc_driver(), master="local[2]")
    session.sparkContext.setLogLevel("ERROR")
    # py4j logs while closing, after pytest has closed the streams it writes to.
    logging.getLogger("py4j").setLevel(logging.WARNING)
    yield session
    session.stop()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)  # nosec B603 B607


@pytest.fixture(scope="session")
def postgres() -> Iterator[dict[str, str]]:
    """A fresh Postgres for the session; the job's DB_* settings for it."""
    if shutil.which("docker") is None:
        pytest.skip("needs Docker")
    port, name = _free_port(), f"radshift-test-pg-{uuid.uuid4().hex[:8]}"
    _docker("run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:5432",
            "-e", f"POSTGRES_PASSWORD={PASSWORD}", "-e", "POSTGRES_DB=radshift",
            POSTGRES_IMAGE).check_returncode()  # fmt: skip
    try:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        # -h 127.0.0.1: ready over TCP, not just the socket the init scripts use.
        while _docker("exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres").returncode:
            assert time.monotonic() < deadline, "Postgres never became ready"
            time.sleep(1)
        yield {"DB_HOST": "127.0.0.1", "DB_PORT": str(port), "DB_NAME": "radshift",
               "DB_USER": "postgres", "DB_PASSWORD": PASSWORD}  # fmt: skip
    finally:
        _docker("rm", "-f", "-v", name)


@pytest.fixture(scope="session")
def pg_engine(postgres) -> Iterator[Engine]:
    """The app's real schema, made from its models."""
    import app.auth.models  # noqa: F401
    import app.posts.models  # noqa: F401

    env = postgres
    engine = create_engine(
        f"postgresql+psycopg2://{env['DB_USER']}:{env['DB_PASSWORD']}@{env['DB_HOST']}:{env['DB_PORT']}/{env['DB_NAME']}"
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
