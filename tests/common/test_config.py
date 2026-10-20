"""Tests for app/common/config.py — env parsing and fail-fast validation."""

import importlib

import pytest


class TestLoadedConfig:
    def test_allowed_origins_is_list(self):
        from app.common.config import Config

        assert isinstance(Config.ALLOWED_ORIGINS, list)
        assert Config.ALLOWED_ORIGINS

    def test_jwt_secret_populated(self):
        from app.common.config import Config

        assert Config.JWT_SECRET_KEY

    def test_db_fields_populated(self):
        from app.common.config import Config

        assert Config.DB_USER
        assert Config.DB_HOST
        assert Config.DB_PORT
        assert Config.DB_NAME

    def test_sqlalchemy_uri_format(self):
        from app.common.config import Config

        # The driver must be explicit: SQLAlchemy 2.1 maps a bare "postgresql://"
        # to psycopg (v3), which isn't installed.
        assert Config.SQLALCHEMY_DATABASE_URI.startswith("postgresql+psycopg2://")


class TestSplitOrigins:
    def test_splits_csv_and_trims(self):
        from app.common.config import _split_origins

        assert _split_origins("http://a.com, http://b.com , http://c.com") == [
            "http://a.com",
            "http://b.com",
            "http://c.com",
        ]

    def test_drops_empty_segments(self):
        from app.common.config import _split_origins

        assert _split_origins("http://a.com,, http://b.com,") == [
            "http://a.com",
            "http://b.com",
        ]


class TestFailFast:
    def test_required_missing_env_raises(self, monkeypatch):
        from app.common.config import ConfigError, _required

        monkeypatch.delenv("PROBABLY_UNSET_XYZZY", raising=False)
        with pytest.raises(ConfigError) as exc:
            _required("PROBABLY_UNSET_XYZZY")
        assert "PROBABLY_UNSET_XYZZY" in str(exc.value)

    def test_required_returns_value_when_set(self, monkeypatch):
        from app.common.config import _required

        monkeypatch.setenv("PROBABLY_SET_XYZZY", "value")
        assert _required("PROBABLY_SET_XYZZY") == "value"

    def test_reimport_without_required_var_raises(self, monkeypatch):
        """Deleting a required env var and re-importing surfaces ConfigError.

        `load_dotenv()` at module top re-reads .env, so we neutralise it for
        this test to make the missing-var condition observable.
        """
        import sys

        monkeypatch.delenv("DB_USER", raising=False)
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)
        sys.modules.pop("app.common.config", None)
        from importlib import import_module

        with pytest.raises(Exception) as exc:
            import_module("app.common.config")
        assert "DB_USER" in str(exc.value)

    def test_reimport_restores_working_config(self, monkeypatch):
        """After the fail-fast test, reset env and re-import for the rest of the suite."""
        import sys

        monkeypatch.setenv("DB_USER", "test")
        sys.modules.pop("app.common.config", None)
        importlib.import_module("app.common.config")
        from app.common.config import Config

        assert Config.DB_USER


class TestRequiredSecret:
    def test_short_secret_is_refused_without_echoing_it(self, monkeypatch):
        from app.common.config import ConfigError, _required_secret

        monkeypatch.setenv("SOME_SECRET_XYZZY", "changeme")
        with pytest.raises(ConfigError) as exc:
            _required_secret("SOME_SECRET_XYZZY", 32)
        assert "SOME_SECRET_XYZZY" in str(exc.value)
        assert "changeme" not in str(exc.value)

    def test_long_enough_secret_is_returned(self, monkeypatch):
        from app.common.config import _required_secret

        monkeypatch.setenv("SOME_SECRET_XYZZY", "x" * 32)
        assert _required_secret("SOME_SECRET_XYZZY", 32) == "x" * 32

    def test_length_is_measured_in_bytes(self, monkeypatch):
        """16 two-byte characters are 32 bytes of key material."""
        from app.common.config import _required_secret

        monkeypatch.setenv("SOME_SECRET_XYZZY", "é" * 16)
        assert _required_secret("SOME_SECRET_XYZZY", 32) == "é" * 16

    def test_missing_secret_is_refused(self, monkeypatch):
        from app.common.config import ConfigError, _required_secret

        monkeypatch.delenv("SOME_SECRET_XYZZY", raising=False)
        with pytest.raises(ConfigError):
            _required_secret("SOME_SECRET_XYZZY", 32)

    def test_jwt_secret_uses_the_minimum(self):
        from app.common.config import Config
        from app.common.constants import MIN_JWT_SECRET_BYTES

        assert len(Config.JWT_SECRET_KEY.encode()) >= MIN_JWT_SECRET_BYTES
