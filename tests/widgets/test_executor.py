"""Tests for app/widgets/executor.py — sandboxed subprocess Python/SQL execution.

Runs real subprocesses (no mocks). Each test gives the sandbox <5s to finish.
"""

import os

from app.widgets.executor import MAX_INPUT_BYTES, execute_python, execute_sql


class TestExecutePython:
    def test_memory_limit_is_enforced(self):
        result = execute_python("x = bytearray(600 * 1024 * 1024)")
        assert result["success"] is False
        assert "MemoryError" in result["stderr"]

    def test_each_run_gets_a_private_workdir_that_is_deleted(self, monkeypatch):
        import app.widgets.executor as executor

        seen: list[tuple[str, str]] = []
        real_run = executor._run_subprocess

        def _spy(cmd, timeout, *, workdir):
            seen.append((cmd[-1], workdir))
            return real_run(cmd, timeout=timeout, workdir=workdir)

        monkeypatch.setattr(executor, "_run_subprocess", _spy)
        execute_python("print(1)")
        execute_sql("SELECT 1")
        assert len(seen) == 2
        (script_a, dir_a), (script_b, dir_b) = seen
        assert dir_a != dir_b, "runs must not share a directory"
        assert os.path.dirname(script_a) == dir_a and os.path.dirname(script_b) == dir_b
        assert not os.path.exists(dir_a) and not os.path.exists(dir_b)

    def test_captures_stdout(self):
        result = execute_python("print('hello world')")
        assert result["success"] is True
        assert "hello world" in result["stdout"]

    def test_reports_error_on_bad_code(self):
        result = execute_python("this is not valid python")
        assert result["success"] is False
        assert result["stderr"]

    def test_rejects_oversize_code(self):
        too_big = "x = 1\n" * (MAX_INPUT_BYTES // 6 + 10)
        result = execute_python(too_big)
        assert result["success"] is False
        assert "maximum size" in result["stderr"].lower()

    def test_duration_is_populated(self):
        result = execute_python("print('done')")
        assert result["duration_ms"] >= 0


class TestExecuteSql:
    def test_basic_select_returns_rows(self):
        result = execute_sql("SELECT 1 AS one, 2 AS two")
        assert result["success"] is True
        assert result["results"][0]["columns"] == ["one", "two"]
        assert result["results"][0]["rows"] == [[1, 2]]

    def test_create_insert_select_flow(self):
        sql = (
            "CREATE TABLE t(id INTEGER, name TEXT);"
            "INSERT INTO t VALUES (1, 'alice'), (2, 'bob');"
            "SELECT COUNT(*) AS n FROM t;"
        )
        result = execute_sql(sql)
        assert result["success"] is True
        count_row = result["results"][-1]
        assert count_row["rows"][0][0] == 2

    def test_bad_sql_reports_error(self):
        result = execute_sql("NOTASQLSTMT;")
        assert result["success"] is False

    def test_oversize_sql_rejected(self):
        too_big = "SELECT 1;\n" * (MAX_INPUT_BYTES // 10 + 10)
        result = execute_sql(too_big)
        assert result["success"] is False
        assert "maximum size" in result["stderr"].lower()


class TestSubprocessErrorPaths:
    """Exercise the _run_subprocess timeout/generic-error branches via mocks."""

    def test_timeout_returns_timeout_message(self):
        import subprocess
        from unittest.mock import patch

        with patch(
            "app.widgets.executor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="x", timeout=5),
        ):
            from app.widgets.executor import execute_python

            result = execute_python("print('x')")
        assert result["success"] is False
        assert "timed out" in result["stderr"].lower()

    def test_subprocess_unexpected_exception_is_handled(self):
        from unittest.mock import patch

        with patch("app.widgets.executor.subprocess.run", side_effect=PermissionError("no python")):
            from app.widgets.executor import EXECUTION_FAILED_MESSAGE, execute_python

            result = execute_python("print('x')")
        assert result["success"] is False
        # A fixed message: the exception text stays in the server log.
        assert result["stderr"] == EXECUTION_FAILED_MESSAGE
        assert "no python" not in result["stderr"]

    def test_python_stdout_not_json_falls_through_to_raw(self):
        """When the wrapper prints non-JSON, execute_python returns raw stdout/stderr."""
        from unittest.mock import MagicMock, patch

        fake_result = MagicMock(stdout="not json at all", stderr="", returncode=0)
        with patch("app.widgets.executor.subprocess.run", return_value=fake_result):
            from app.widgets.executor import execute_python

            result = execute_python("ignored")
        assert result["stdout"] == "not json at all"
        assert result["success"] is True

    def test_sql_stdout_not_json_reports_failure(self):
        """When the SQL wrapper prints non-JSON, execute_sql marks failure."""
        from unittest.mock import MagicMock, patch

        fake_result = MagicMock(stdout="garbage", stderr="", returncode=0)
        with patch("app.widgets.executor.subprocess.run", return_value=fake_result):
            from app.widgets.executor import execute_sql

            result = execute_sql("SELECT 1")
        assert result["success"] is False
        assert result["results"] == []


class TestSubprocessStartFailure:
    """Regression: when the interpreter can't be started, the caller used to
    get the raw exception text (a server path) back as stderr (rule 10)."""

    def test_missing_binary_reports_a_fixed_message(self, tmp_path):
        from app.widgets.executor import EXECUTION_FAILED_MESSAGE, _run_subprocess

        missing = str(tmp_path / "no-such-interpreter")

        stdout, stderr, returncode = _run_subprocess([missing], workdir=str(tmp_path))

        assert (stdout, stderr, returncode) == ("", EXECUTION_FAILED_MESSAGE, -1)
        assert missing not in stderr

    def test_the_cause_is_logged(self, tmp_path, caplog):
        from app.widgets.executor import _run_subprocess

        missing = str(tmp_path / "no-such-interpreter")

        with caplog.at_level("ERROR", logger="app.widgets.executor"):
            _run_subprocess([missing], workdir=str(tmp_path))

        assert "Subprocess execution failed" in caplog.text
        assert "no-such-interpreter" in caplog.text
