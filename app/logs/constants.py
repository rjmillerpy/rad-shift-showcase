"""Names and limits for structured logging (app/logs/)."""

import logging
import re

from app.metrics.service import METRICS_PATH

# Environment variables read at startup (app/common/config.py).
LOG_RENDERER_ENV_VAR = "LOG_RENDERER"
LOG_LEVEL_ENV_VAR = "LOG_LEVEL"

# One JSON object per line, for Loki and CloudWatch; the default, so a
# deployed container never ships unparseable text by accident.
JSON_RENDERER = "json"
# Coloured, aligned lines for a developer's terminal.
CONSOLE_RENDERER = "console"
DEFAULT_LOG_LEVEL = "INFO"

# Chatty at INFO (every SQL statement); only their warnings are kept.
QUIET_LOGGERS = ("sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.dialects")
# Uvicorn installs its own text handlers; these are pointed at the root's.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error")
# Replaced by the request log (app/logs/middleware.py), which has the
# route template, request id and user that uvicorn's line lacks.
UVICORN_ACCESS_LOGGER = "uvicorn.access"

# Read from the caller and echoed on every response.
REQUEST_ID_HEADER = "x-request-id"
# A caller's id is kept only if it looks like one (UUIDs, trace ids, Heroku
# and AWS ids all fit); anything else, including text that could forge a log
# field, is replaced with a fresh id.
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")

LOG_EVENT_REQUEST = "http.request"
# Hit every few seconds by health checks and the Prometheus scrape; logged
# at DEBUG so they don't bury real traffic (LOG_LEVEL=DEBUG shows them).
QUIET_ROUTES = frozenset({"/health", "/health/live", METRICS_PATH})
QUIET_LEVEL = logging.DEBUG
# Requests answered with a server error are logged at ERROR.
SERVER_ERROR_LEVEL = logging.ERROR
