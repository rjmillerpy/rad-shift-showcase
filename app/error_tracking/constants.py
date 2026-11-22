"""Settings and names for error tracking with Sentry (roadmap item 25)."""

# Environment variables read at startup (app/common/config.py). The SDK
# reads SENTRY_RELEASE itself; the image sets it (Dockerfile). It stays out
# of .env.example: a blank line there would override the image's value.
SENTRY_DSN_ENV_VAR = "SENTRY_DSN"
SENTRY_ENVIRONMENT_ENV_VAR = "SENTRY_ENVIRONMENT"
SENTRY_TRACES_SAMPLE_RATE_ENV_VAR = "SENTRY_TRACES_SAMPLE_RATE"

DEFAULT_ENVIRONMENT = "local"
# Errors only by default: performance traces count against a separate quota.
DEFAULT_TRACES_SAMPLE_RATE = 0.0

# Already reported another way, so their ERROR lines would be duplicate
# events: the request log line for a 5xx (the exception is its own event)
# and uvicorn's "Exception in ASGI application" traceback.
IGNORED_LOGGERS = ("app.logs.middleware", "uvicorn.error")

# The tag that ties a Sentry event to the request's log lines in Loki.
REQUEST_ID_TAG = "request_id"
