"""Fixtures for the health tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture()
def unreachable_db(tmp_path):
    """A real Session whose database can't be opened, so every query raises a
    genuine driver error (sqlite: "unable to open database file")."""
    missing = tmp_path / "no-such-directory" / "app.db"
    engine = create_engine(f"sqlite:///{missing}")
    with Session(engine) as session:
        yield session
    engine.dispose()
