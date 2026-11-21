"""Tests for app/logs/setup.py: what actually reaches stderr."""

import json
import logging
import sys

import pytest
import structlog

from app.logs.constants import (
    CONSOLE_RENDERER,
    JSON_RENDERER,
    QUIET_LOGGERS,
    UVICORN_ACCESS_LOGGER,
    UVICORN_LOGGERS,
)
from app.logs.setup import LogConfigError, configure_logging

pytestmark = pytest.mark.usefixtures("restore_logging")


class TestJsonLines:
    def test_a_stdlib_record_becomes_one_json_object(self, json_logs):
        logging.getLogger("radshift.test").info("thing.happened")
        (line,) = json_logs()
        assert line["event"] == "thing.happened"
        assert line["level"] == "info"
        assert line["logger"] == "radshift.test"
        assert line["timestamp"].endswith("Z")

    def test_extra_fields_become_keys(self, json_logs):
        """The old text format silently dropped these."""
        logging.getLogger("radshift.test").info("fetch", extra={"entity": "wanderer", "count": 3})
        (line,) = json_logs()
        assert line["entity"] == "wanderer" and line["count"] == 3

    def test_printf_arguments_are_interpolated(self, json_logs):
        logging.getLogger("radshift.test").info("Registered %d routers", 14)
        assert json_logs()[0]["event"] == "Registered 14 routers"

    def test_context_bound_values_are_added(self, json_logs):
        structlog.contextvars.bind_contextvars(request_id="abc123")
        logging.getLogger("radshift.test").info("inside a request")
        assert json_logs()[0]["request_id"] == "abc123"

    def test_an_exception_is_one_string_field(self, json_logs):
        try:
            raise ValueError("bad value")
        except ValueError:
            logging.getLogger("radshift.test").exception("failed")
        (line,) = json_logs()
        assert line["level"] == "error"
        assert "Traceback" in line["exception"] and "ValueError: bad value" in line["exception"]

    def test_a_multi_line_message_stays_on_one_line(self, json_logs):
        """A forged second line can't pass for a separate log entry."""
        logging.getLogger("radshift.test").info('ok\n{"level": "info", "event": "forged"}')
        lines = json_logs()
        assert len(lines) == 1 and lines[0]["event"].startswith("ok\n")

    def test_structlog_loggers_render_the_same_way(self, json_logs):
        structlog.get_logger("radshift.native").info("native", answer=42)
        (line,) = json_logs()
        assert line == {
            "event": "native",
            "answer": 42,
            "logger": "radshift.native",
            "level": "info",
            "timestamp": line["timestamp"],
        }


class TestConsole:
    def test_console_lines_are_readable_text(self, configure_logging_into_buffer):
        buffer = configure_logging_into_buffer(CONSOLE_RENDERER)
        logging.getLogger("radshift.test").warning("hello", extra={"k": 1})
        output = buffer.getvalue()
        assert "hello" in output and "k" in output
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)


class TestLevels:
    def test_records_below_the_level_are_dropped(self, configure_logging_into_buffer):
        buffer = configure_logging_into_buffer(JSON_RENDERER, "warning")
        logging.getLogger("radshift.test").info("dropped")
        logging.getLogger("radshift.test").warning("kept")
        assert [json.loads(line)["event"] for line in buffer.getvalue().splitlines()] == ["kept"]

    def test_sql_loggers_keep_only_warnings(self, json_logs):
        for name in QUIET_LOGGERS:
            assert logging.getLogger(name).level == logging.WARNING


class TestUvicorn:
    def test_uvicorn_lines_go_through_the_json_handler(self, json_logs):
        for name in UVICORN_LOGGERS:
            uvicorn_logger = logging.getLogger(name)
            assert uvicorn_logger.handlers == [] and uvicorn_logger.propagate
        logging.getLogger("uvicorn.error").info("Started server process")
        assert json_logs()[0]["event"] == "Started server process"

    def test_uvicorn_access_lines_are_dropped(self, json_logs):
        """The request log replaces them."""
        logging.getLogger(UVICORN_ACCESS_LOGGER).info('127.0.0.1 - "GET / HTTP/1.1" 200')
        assert json_logs() == []


class TestStream:
    def test_writes_to_stderr(self):
        configure_logging()
        (handler,) = logging.getLogger().handlers
        assert isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr


class TestReconfiguring:
    def test_calling_again_keeps_one_handler(self):
        configure_logging()
        configure_logging()
        assert len(logging.getLogger().handlers) == 1


class TestBadSettings:
    def test_unknown_renderer(self):
        with pytest.raises(LogConfigError, match="'xml'"):
            configure_logging("xml")

    def test_unknown_level(self):
        with pytest.raises(LogConfigError, match="'LOUD'"):
            configure_logging(JSON_RENDERER, "LOUD")

    @pytest.mark.parametrize("settings", [("xml",), (JSON_RENDERER, "LOUD")])
    def test_a_bad_setting_changes_nothing(self, settings):
        handlers = logging.getLogger().handlers[:]
        with pytest.raises(LogConfigError):
            configure_logging(*settings)
        assert logging.getLogger().handlers == handlers
