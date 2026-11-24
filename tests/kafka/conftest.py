"""A real Kafka broker for tests/kafka/: the image compose.yaml runs, on a free port.

Marked `kafka` (pyproject.toml): they need Docker, so the default run skips
them and CI runs them in a step of their own (pytest -m kafka).
"""

import shutil
import socket
import subprocess  # nosec B404 - fixed docker commands, never a shell
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml
from confluent_kafka.admin import AdminClient

from app.engagement.topics import ensure_topics

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "compose.yaml"
READY_TIMEOUT_SECONDS = 90


def compose_kafka() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())["services"]["kafka"]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def docker(*args: str) -> str:
    return subprocess.run(  # nosec B603 B607 - fixed docker commands
        ["docker", *args], check=True, capture_output=True, text=True, timeout=120
    ).stdout


@pytest.fixture(scope="session")
def bootstrap_servers() -> Iterator[str]:
    """A fresh single-node broker for the session, configured as in compose.yaml."""
    if shutil.which("docker") is None:
        pytest.skip("needs Docker")
    service = compose_kafka()
    port = free_port()
    environment = {
        **service["environment"],
        # Reachable from the host on the free port instead of as kafka:9092.
        "KAFKA_LISTENERS": f"PLAINTEXT://:{port},CONTROLLER://:9093",
        "KAFKA_ADVERTISED_LISTENERS": f"PLAINTEXT://127.0.0.1:{port}",
    }
    name = f"radshift-test-kafka-{uuid.uuid4().hex[:8]}"
    env_args = [arg for key, value in environment.items() for arg in ("-e", f"{key}={value}")]
    docker("run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:{port}", *env_args,
           service["image"])  # fmt: skip
    try:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while True:
            try:
                docker("exec", name, "/opt/kafka/bin/kafka-broker-api-versions.sh",
                       "--bootstrap-server", f"localhost:{port}")  # fmt: skip
                break
            except subprocess.CalledProcessError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        servers = f"127.0.0.1:{port}"
        ensure_topics(AdminClient({"bootstrap.servers": servers}))
        yield servers
    finally:
        docker("rm", "-f", name)


@pytest.fixture()
def group_id() -> str:
    """A consumer group of its own per test: it starts from the oldest event."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def sessions(db_session) -> Callable:
    @contextmanager
    def _factory():
        yield db_session

    return _factory
