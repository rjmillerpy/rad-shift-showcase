"""Fixtures for the metrics tests."""

import pytest
from prometheus_client import CollectorRegistry
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.common.db import get_db
from app.metrics.service import RequestMetrics


@pytest.fixture()
def registry():
    """A registry of its own, so counts don't leak in from other tests."""
    return CollectorRegistry()


@pytest.fixture()
def request_metrics(registry):
    return RequestMetrics(registry)


def sample_value(exposition: str, name: str, **labels: str) -> float:
    """One sample from a scrape body, or 0.0 when the series doesn't exist yet."""
    for family in text_string_to_metric_families(exposition):
        for sample in family.samples:
            if sample.name == name and sample.labels == labels:
                return sample.value
    return 0.0


@pytest.fixture()
def unreachable_health_db(client, tmp_path):
    """The real app with its database dependency pointed at one that can't be
    opened, so /health genuinely fails with a 503."""
    engine = create_engine(f"sqlite:///{tmp_path / 'no-such-directory' / 'app.db'}")
    with Session(engine) as session:
        client.app.dependency_overrides[get_db] = lambda: session
        yield session
    engine.dispose()
