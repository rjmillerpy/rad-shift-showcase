"""SQLAlchemy engine, session factory, `Base`, and the FastAPI `get_db` dep."""

import logging
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.common.config import Config
from app.common.constants import DB_CONNECT_TIMEOUT_SECONDS, DB_POOL_RECYCLE_SECONDS

logger = logging.getLogger(__name__)


def build_engine(url: str, connect_timeout: int = DB_CONNECT_TIMEOUT_SECONDS) -> Engine:
    """Engine for the app's Postgres (psycopg2).

    pool_pre_ping: test each pooled connection before handing it out, so a
    database restart or idle disconnect costs a reconnect, not a failed
    request. pool_recycle: replace connections older than the idle cutoffs.
    connect_timeout: an unreachable server fails in seconds, not minutes.
    """
    return create_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=DB_POOL_RECYCLE_SECONDS,
        connect_args={"connect_timeout": connect_timeout},
    )


DATABASE_URL: str = Config.SQLALCHEMY_DATABASE_URI
engine = build_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a session and always close it.

    Rolls back on unhandled exceptions so a partially failed request never
    poisons the next reuse of the session pool.
    """
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        logger.exception("Database session error during cleanup")
        db.rollback()
        raise
    finally:
        db.close()
