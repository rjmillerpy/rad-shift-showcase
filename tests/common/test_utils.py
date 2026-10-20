"""Tests for app/common/utils.py — get_user and require_verified.

Duplicated content that previously lived here (Config, get_db, S3, User)
now lives in the correct mirror files (test_config.py, test_db.py, test_s3.py,
tests/auth/test_models.py) per rule 48.
"""

import pytest
from fastapi import HTTPException

from app.common.utils import get_user, require_verified


class TestGetUser:
    def test_returns_existing_user(self, db_session, create_user):
        create_user(username="alice")
        user = get_user("alice", db_session)
        assert user is not None
        assert user.username == "alice"

    def test_returns_none_for_missing_user(self, db_session):
        assert get_user("does_not_exist", db_session) is None

    def test_is_case_sensitive(self, db_session, create_user):
        create_user(username="alice")
        # Postgres would be case-sensitive; SQLite is by default too.
        assert get_user("ALICE", db_session) is None


class TestRequireVerified:
    def test_passes_when_verified(self, db_session, create_user):
        user = create_user(username="verified_user")
        # create_user fixture sets email_verified=True.
        require_verified(user)  # no raise

    def test_raises_403_when_unverified(self, db_session, create_user):
        user = create_user(username="unverified_user")
        user.email_verified = False
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            require_verified(user)
        assert exc.value.status_code == 403
        assert "verify" in exc.value.detail.lower()
