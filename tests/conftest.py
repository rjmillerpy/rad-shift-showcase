"""
Shared fixtures for the rad-shift test suite.

* In-memory SQLite database (overrides get_db)
* FastAPI TestClient wired to the real app
* JWT helper that mints valid access tokens for any username
* Convenience fixtures: create_user, create_post, auth_header
* S3 calls are globally mocked so no network traffic escapes
"""

import json
import os
import time
from collections.abc import Callable, Iterator, Mapping
from unittest.mock import MagicMock, patch

import pytest
from openfeature import api
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Environment variables required BEFORE any app import touches Config / boto3
# ---------------------------------------------------------------------------
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault(
    "JWT_SECRET", "test-only-secret-at-least-32-bytes-long"
)  # PyJWT 2 warns below 32
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

# ---------------------------------------------------------------------------
# SQLite in-memory engine using StaticPool so every connection shares the
# same underlying database (required for in-memory SQLite).
# ---------------------------------------------------------------------------
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    # SQLite lacks GREATEST / COALESCE behaves the same, but GREATEST is missing.
    dbapi_conn.create_function("greatest", 2, lambda a, b: max(a, b))


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# ---------------------------------------------------------------------------
# Patch S3 globally before any module-level boto3 client is created
# ---------------------------------------------------------------------------
_s3_mock = MagicMock()
_s3_patcher = patch("app.common.s3.s3_client", _s3_mock)
_s3_patcher.start()

# The real function, kept before the patch below replaces it everywhere, so
# its own tests (tests/common/test_s3.py) can call it against the mock client.
import app.common.s3 as _s3_module  # noqa: E402

REAL_UPLOAD_FILEOBJ_TO_S3 = _s3_module.upload_fileobj_to_s3


# Patch upload_fileobj_to_s3 everywhere it is imported
def _upload_side_effect(fileobj, s3_key, content_type="image/jpeg"):
    return f"https://test-bucket.s3.amazonaws.com/{s3_key}"


_upload_patcher_common = patch(
    "app.common.s3.upload_fileobj_to_s3", side_effect=_upload_side_effect
)
_upload_patcher_posts = patch(
    "app.posts.uploads.upload_fileobj_to_s3", side_effect=_upload_side_effect
)
_upload_patcher_profile = patch(
    "app.profile.service.upload_fileobj_to_s3", side_effect=_upload_side_effect
)
_upload_patcher_avatar = patch(
    "app.avatar.generator.upload_fileobj_to_s3", side_effect=_upload_side_effect
)
_upload_patcher_common.start()
_upload_patcher_posts.start()
_upload_patcher_profile.start()
_upload_patcher_avatar.start()

# ---------------------------------------------------------------------------
# Patch require_verified globally so interaction endpoints don't block on
# Only mock truly external boundaries: email sending and S3.
# require_verified is NOT mocked — test users are auto-verified via DB fixture.
# ---------------------------------------------------------------------------

# Patch send_verification_email globally to prevent any actual sending
_send_email_patcher = patch("app.auth.service.send_verification_email", return_value=True)
_send_email_patcher.start()

# ---------------------------------------------------------------------------
# Patch the db module BEFORE importing app.main (which calls create_tables
# at module level and would try to connect to PostgreSQL).
# ---------------------------------------------------------------------------
import app.common.db as _db_mod  # noqa: E402

_db_mod.engine = test_engine
_db_mod.SessionLocal = TestingSessionLocal
_db_mod.create_tables = lambda: None  # no-op; tables created per-test below

# Also patch the already-bound name inside app.main
import app.main as _main_mod  # noqa: E402

_main_mod.create_tables = lambda: None

# bcrypt's minimum cost (4) instead of production's 12: about 1 ms per hash
# instead of 200 ms. Tests create thousands of users and check behaviour, not
# hash strength; this alone cut the suite from 397 s to 96 s.
# tests/auth/test_service.py guards the production value.
import app.auth.constants as _auth_constants  # noqa: E402

_auth_constants.BCRYPT_ROUNDS = 4

import app.admin.models  # noqa: E402,F401

# Imported for their side effect: registering tables on Base.metadata so the
# per-test create_all() builds them.
import app.blog.models  # noqa: E402,F401
import app.widgets.models  # noqa: E402,F401
from app.auth.models import User  # noqa: E402
from app.common.db import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.plugins import Edition, use_edition  # noqa: E402
from app.posts.models import PostModel  # noqa: E402
from tests.helpers import FLAGS_FILE, serve_flags_file  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@event.listens_for(User, "after_insert")
def _auto_verify_user(mapper, connection, target):
    """Auto-verify users in tests so require_verified passes.
    This avoids mocking internal functions — the real require_verified runs,
    but test users are always verified via this DB-level hook."""
    if not target.email_verified:
        connection.execute(
            User.__table__.update()
            .where(User.__table__.c.id == target.id)
            .values(email_verified=True)
        )


# ── Feature flags ───────────────────────────────────────────────────────────
#
# flagd is an external service, so tests don't run one. They use the same
# OpenFeature flagd provider the app uses, reading the flags file directly
# (its FILE mode) instead of syncing it from the daemon: every test sees the
# checked-in flags, evaluated by the real engine.


@pytest.fixture(scope="session", autouse=True)
def _feature_flags_from_the_repo() -> Iterator[None]:
    serve_flags_file(FLAGS_FILE)
    yield
    api.shutdown()


@pytest.fixture()
def set_flags(tmp_path) -> Iterator[Callable[[Mapping], None]]:
    """Pin flags for one test: set_flags({Flag.CHRONICLE_LLM_NARRATION: True}).

    Serves a copy of the flags file in which those flags have no targeting
    and default to the given value; the repo's file comes back afterwards.
    """

    def _set(values: Mapping) -> None:
        document = json.loads(FLAGS_FILE.read_text())
        for flag, value in values.items():
            entry = document["flags"][flag.value]
            entry.pop("targeting", None)
            entry["defaultVariant"] = next(k for k, v in entry["variants"].items() if v is value)
        pinned = tmp_path / "flags.flagd.json"
        pinned.write_text(json.dumps(document))
        serve_flags_file(pinned)

    yield _set
    serve_flags_file(FLAGS_FILE)


@pytest.fixture(autouse=True)
def test_edition() -> Iterator[Edition]:
    """The edition every test runs on. Public tests run on the public one even
    when the private package is installed, so they never depend on (or
    reveal) private behaviour; the private edition's tests override this fixture."""
    from app.baseline import EDITION

    with use_edition(EDITION) as chosen:
        yield chosen


@pytest.fixture(autouse=True)
def _setup_db():
    """Create all tables before each test, drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session() -> Session:
    """Provide a raw SQLAlchemy session for direct DB manipulation."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    """TestClient whose get_db dependency is overridden to use SQLite."""
    app = create_app()

    def _override_get_db():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db

    from starlette.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_header(client):
    """Factory fixture: returns {"Authorization": "Bearer <token>"} for a username.

    The user MUST already exist in the DB (use create_user first).
    """
    from app.common.auth_jwt import AuthJWT

    def _make(username: str) -> dict:
        token = AuthJWT().create_access_token(subject=username)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture()
def create_user(db_session):
    """Factory fixture: inserts a User row and returns it."""

    def _make(
        username: str = "testuser",
        password: str = "password123",
        email: str | None = None,
        is_admin: bool = False,
    ) -> User:
        user = User(
            username=username,
            email=email or f"{username}@test.com",
            email_verified=True,
            is_admin=is_admin,
        )
        user.set_password(password)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture()
def create_post(db_session):
    """Factory fixture: inserts a PostModel row and returns it."""

    def _make(
        user: User,
        text: str = "Hello world",
        metadata: dict | None = None,
        is_draft: bool = False,
        is_reply: bool = False,
        parent_post_id: int | None = None,
        unix_timestamp: int | None = None,
    ) -> PostModel:
        post = PostModel(
            text=text,
            post_metadata=json.dumps(metadata or {}),
            unix_timestamp=unix_timestamp or int(time.time()),
            user=user,
            is_draft=is_draft,
            is_reply=is_reply,
            parent_post_id=parent_post_id,
        )
        db_session.add(post)
        db_session.commit()
        db_session.refresh(post)
        return post

    return _make
