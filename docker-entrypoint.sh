#!/bin/sh
# Container entrypoint: prepare the database schema, then hand off to the
# command (uvicorn by default, see CMD in the Dockerfile).
#
# `exec` replaces this shell with the command so it runs as PID 1 and
# receives SIGTERM directly when you `docker compose stop`.
set -e

python scripts/prepare_db.py

exec "$@"
