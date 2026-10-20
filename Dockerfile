# Backend image: FastAPI + SQLAlchemy app served by uvicorn on port 5000.
#
#   docker build -t radshift-backend .
#
# Multi-stage: `builder` installs the Python dependencies with uv; `runtime`
# starts from a clean base and copies in only the virtualenv and the files the
# app reads at runtime. Build tooling, the lockfile, tests and local caches
# never reach the final image.

# uv comes from Astral's image (a named stage so Dependabot can bump it).
FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

# ── builder: resolve and install dependencies into /opt/venv ────────────────
FROM python:3.12-slim AS builder

# UV_PROJECT_ENVIRONMENT: build the venv at the path the runtime stage uses
# (venvs hold absolute paths, so it must not move).
# UV_LINK_MODE=copy: the cache is a build mount, so copy files out of it
# instead of hard-linking to something that won't exist in the image.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy

WORKDIR /build

# Only the dependency files: this layer is cached until one of them changes,
# so editing app code doesn't trigger a reinstall.
# --locked: exactly uv.lock (fails if it is stale); --no-dev: no test or lint
# tools; --no-install-project / --no-install-workspace: third-party only.
COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --no-install-workspace


# ── runtime: what actually runs ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# PYTHONDONTWRITEBYTECODE: no .pyc files (the app user can't write them anyway).
# PYTHONUNBUFFERED: logs reach `docker logs` immediately.
# PLAYWRIGHT_BROWSERS_PATH: shared location so the non-root user can use the browsers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# ffprobe (from ffmpeg) extracts duration/dimensions from uploaded video.
# Installed with apt, not copied from a build stage: copying ffprobe plus the
# 210 libraries it links would save ~240 MB, but files outside the package
# database are invisible to image vulnerability scanners.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv


# Run as an unprivileged user. UID 1000 matches the usual first desktop user,
# so a bind-mounted ~/.aws (see compose.yaml) is readable.
RUN useradd --create-home --uid 1000 app

# An explicit list, not `COPY . .`: a new file in the repo can't end up in the
# image by accident (a 48 MB .mypy_cache did). Left root-owned, so the app
# user can read its code but not change it; runtime writes go to /tmp.
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app
COPY --chmod=755 docker-entrypoint.sh ./

USER app

EXPOSE 5000

ENTRYPOINT ["./docker-entrypoint.sh"]
# One worker on purpose: each worker would start its own generator scheduler.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
