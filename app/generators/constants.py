"""Shared enums and constants for the generator/scraper domain."""

from enum import Enum


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# Failure handling
MAX_CONSECUTIVE_FAILURES = 5
MAX_ERROR_MESSAGE_CHARS = 2000

# HTTP status codes returned by the scraper orchestration layer.
FETCH_FAILURE_STATUS = 502
GENERIC_FAILURE_STATUS = 500

# Playwright / analyzer defaults
DEFAULT_BROWSER_ENGINE = "chromium"

# Analyzer (Claude selector generation) tunables
ANALYZER_MAX_TOKENS = 1024
ANALYZER_API_TIMEOUT_SECONDS = 30

# Scheduler tunables
SCHEDULER_POLL_INTERVAL_SECONDS = 60
SCHEDULER_MAX_SOURCES_PER_TICK = 5
SCHEDULER_JOIN_TIMEOUT_SECONDS = 10

# API pagination bounds for the admin generator surface.
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
DEFAULT_RUN_LIMIT = 20
MAX_RUN_LIMIT = 200

# Prefix used when every fallback endpoint fails inside `fetch_with_fallbacks`.
ALL_ENDPOINTS_FAILED_PREFIX = "All endpoints failed — "

# Answered for the "web" platform when the edition has no web scraper (app/generators/web.py).
WEB_SCRAPING_UNAVAILABLE = "Web scraping isn't available in this edition; use an RSS source."
