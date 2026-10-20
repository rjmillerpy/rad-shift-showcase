"""Server-side widget code execution.

Runs Python and SQL code in a child process with:
- 5-second wall-clock timeout and CPU-time limit
- Address-space, file-size, and process-count rlimits
- Captured stdout/stderr

This is NOT a security sandbox. Stripping builtins is escapable
(e.g. via ``object.__subclasses__()``), and the child still has the API
host's network and filesystem access. The rlimits only contain resource
abuse. The views therefore keep this feature disabled by default and
admin-only when enabled; real isolation needs a separate container/VM.
"""

import json
import logging
import os
import resource
import subprocess  # nosec B404 - running user code is this module's purpose; see docstring
import sys
import tempfile
import time

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT_SECONDS = 5
# Shown to the caller when the subprocess itself could not be started.
EXECUTION_FAILED_MESSAGE = "Execution failed to start"
MAX_OUTPUT_BYTES = 50000  # 50KB max output
MAX_INPUT_BYTES = 500000  # 500KB max code

# Child-process rlimits (defence in depth, see module docstring).
CHILD_MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
CHILD_FILE_SIZE_LIMIT_BYTES = 1024 * 1024
CHILD_MAX_PROCESSES = 0  # no fork/exec from user code

# Python execution uses subprocess with restricted builtins
PYTHON_WRAPPER = """
import sys, json, io

_capture_out = io.StringIO()
_capture_err = io.StringIO()

# Restricted builtins — remove dangerous functions
_blocked = {"exec", "eval", "compile", "__import__", "open", "input", "breakpoint"}
_safe_builtins = {k: v for k, v in __builtins__.__dict__.items() if k not in _blocked}

# Provide a safe print that writes to our capture buffer
def _safe_print(*args, **kwargs):
    kwargs.pop("file", None)
    print(*args, file=_capture_out, **kwargs)

_safe_builtins["print"] = _safe_print

_input_data = {input_json}

try:
    _code = {code_json}
    _globals = {"__builtins__": _safe_builtins}
    if _input_data is not None:
        _globals["INPUT"] = _input_data
    exec(_code, _globals)
except Exception as e:
    _capture_err.write(f"{type(e).__name__}: {e}")

result = {"stdout": _capture_out.getvalue()[:50000], "stderr": _capture_err.getvalue()[:10000]}
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__
print(json.dumps(result))
"""

SQL_WRAPPER = """
import sqlite3, json, sys

db = sqlite3.connect(":memory:")
cursor = db.cursor()
results = []
for stmt in {code_json}.split(";"):
    stmt = stmt.strip()
    if not stmt:
        continue
    try:
        cursor.execute(stmt)
        if cursor.description:
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            results.append({"columns": cols, "rows": [list(r) for r in rows]})
        else:
            results.append({"affected": cursor.rowcount})
        db.commit()
    except Exception as e:
        results.append({"error": str(e)})

print(json.dumps({"results": results}))
"""


def _limit_child_resources() -> None:
    """preexec_fn: apply rlimits inside the child before exec."""
    resource.setrlimit(resource.RLIMIT_AS, (CHILD_MEMORY_LIMIT_BYTES,) * 2)
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (EXECUTION_TIMEOUT_SECONDS, EXECUTION_TIMEOUT_SECONDS),
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (CHILD_FILE_SIZE_LIMIT_BYTES,) * 2)
    resource.setrlimit(resource.RLIMIT_NPROC, (CHILD_MAX_PROCESSES,) * 2)


def _run_script(source: str) -> tuple[str, str, int, int]:
    """Run `source` in a private temporary directory that is deleted afterwards.

    The child's cwd, HOME and TMPDIR all point at that directory, so runs can't
    see each other's files or race on names in the shared /tmp, and anything
    the user code writes is removed with it.

    Returns (stdout, stderr, return_code, duration_ms).
    """
    with tempfile.TemporaryDirectory(prefix="widget-exec-", ignore_cleanup_errors=True) as workdir:
        script_path = os.path.join(workdir, "main.py")
        with open(script_path, "w") as f:
            f.write(source)
        start = time.monotonic()
        stdout, stderr, returncode = _run_subprocess(
            [sys.executable, script_path], timeout=EXECUTION_TIMEOUT_SECONDS, workdir=workdir
        )
        duration_ms = int((time.monotonic() - start) * 1000)
    return stdout, stderr, returncode, duration_ms


def _run_subprocess(
    cmd: list[str], timeout: int = EXECUTION_TIMEOUT_SECONDS, *, workdir: str
) -> tuple[str, str, int]:
    """Run a subprocess with timeout and capture output.

    Returns (stdout, stderr, return_code).
    """
    try:
        result = subprocess.run(  # nosec B603 - runs user code on purpose; feature is off by default and admin-only
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
            preexec_fn=_limit_child_resources,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": workdir,
                "TMPDIR": workdir,
            },
        )
        stdout = result.stdout[:MAX_OUTPUT_BYTES] if result.stdout else ""
        stderr = result.stderr[:MAX_OUTPUT_BYTES] if result.stderr else ""
        return stdout, stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Execution timed out after {timeout} seconds", -1
    except (OSError, subprocess.SubprocessError):
        # The interpreter couldn't be started (missing binary, resource limits
        # refused in preexec_fn). The detail holds server paths, so it goes to
        # the log; the caller's stderr only says that it failed (rule 10).
        logger.exception("Subprocess execution failed")
        return "", EXECUTION_FAILED_MESSAGE, -1


def execute_python(code: str, input_data: str | None = None) -> dict:
    """Run Python code in a restricted subprocess.

    Returns {"stdout": str, "stderr": str, "duration_ms": int, "success": bool}.
    """
    if len(code) > MAX_INPUT_BYTES:
        return {
            "stdout": "",
            "stderr": "Code exceeds maximum size limit",
            "duration_ms": 0,
            "success": False,
        }

    code_json = json.dumps(code)
    input_json = json.dumps(input_data) if input_data is not None else "None"
    wrapper = PYTHON_WRAPPER.replace("{code_json}", code_json).replace("{input_json}", input_json)

    stdout, stderr, returncode, duration_ms = _run_script(wrapper)

    # Try to parse the JSON result from stdout
    try:
        result = json.loads(stdout.strip())
        return {
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "") or stderr,
            "duration_ms": duration_ms,
            "success": returncode == 0 and not result.get("stderr"),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "success": returncode == 0 and not stderr,
        }


def execute_sql(code: str) -> dict:
    """Run SQL code using Python's sqlite3 in a subprocess.

    Returns {"results": list[dict], "stderr": str, "duration_ms": int, "success": bool}.
    """
    if len(code) > MAX_INPUT_BYTES:
        return {
            "results": [],
            "stderr": "Code exceeds maximum size limit",
            "duration_ms": 0,
            "success": False,
        }

    code_json = json.dumps(code)
    wrapper = SQL_WRAPPER.replace("{code_json}", code_json)

    stdout, stderr, returncode, duration_ms = _run_script(wrapper)

    try:
        result = json.loads(stdout.strip())
        has_errors = any("error" in r for r in result.get("results", []))
        return {
            "results": result.get("results", []),
            "stderr": stderr,
            "duration_ms": duration_ms,
            "success": returncode == 0 and not has_errors,
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "results": [],
            "stderr": stderr or stdout,
            "duration_ms": duration_ms,
            "success": False,
        }
