"""Application configuration loaded from environment variables at import time.

Missing required variables raise `ConfigError` immediately so misconfiguration
surfaces at boot rather than as a cryptic downstream failure.
"""

import logging
import os
import urllib.parse

from dotenv import load_dotenv

from app.common.constants import (
    DEFAULT_ALLOWED_ORIGIN,
    LOG_DATEFMT,
    LOG_FORMAT,
    MIN_JWT_SECRET_BYTES,
)

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
for noisy in ("sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.dialects"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


load_dotenv()


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing or empty."""


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Required environment variable {name!r} is not set")
    return value


def _required_secret(name: str, min_bytes: int) -> str:
    """A required secret that must also be long enough. The error names the
    variable and the rule, never the value."""
    value = _required(name)
    if len(value.encode("utf-8")) < min_bytes:
        raise ConfigError(
            f"{name!r} is too short: use at least {min_bytes} bytes (e.g. `openssl rand -hex 32`)"
        )
    return value


def _split_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class Config:
    DEBUG: bool = True
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    DB_USER: str = _required("DB_USER")
    DB_PASSWORD: str = urllib.parse.quote(_required("DB_PASSWORD"))
    DB_HOST: str = _required("DB_HOST")
    DB_PORT: str = _required("DB_PORT")
    DB_NAME: str = _required("DB_NAME")
    JWT_SECRET_KEY: str = _required_secret("JWT_SECRET", MIN_JWT_SECRET_BYTES)

    ALLOWED_ORIGINS: list[str] = _split_origins(
        os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGIN)
    )

    SQLALCHEMY_DATABASE_URI: str = (
        # Driver named explicitly: SQLAlchemy 2.1 changed the default for a bare
        # "postgresql://" from psycopg2 to psycopg (v3), which isn't installed.
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
