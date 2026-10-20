"""Tests for app/amble/content/models.py — real rows in the test database."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.amble.content.models import AmbleBindingOverride, AmbleContentCursor

BINDING_JSON = {"kind": "category", "tags": ["coffee"], "weight": 1.0}


class TestContentCursor:
    def test_offset_defaults_to_zero_and_timestamps_are_set(self, db_session, create_user):
        user = create_user(username="walker")
        cursor = AmbleContentCursor(user_id=user.id, entity_id="cafe")
        db_session.add(cursor)
        db_session.commit()

        assert cursor.offset_val == 0
        assert cursor.created_at is not None
        assert cursor.updated_at is not None

    def test_one_cursor_per_user_and_entity(self, db_session, create_user):
        user = create_user(username="walker")
        db_session.add(AmbleContentCursor(user_id=user.id, entity_id="cafe"))
        db_session.commit()

        db_session.add(AmbleContentCursor(user_id=user.id, entity_id="cafe"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_same_entity_for_two_users_is_allowed(self, db_session, create_user):
        first, second = create_user(username="walker_a"), create_user(username="walker_b")
        db_session.add_all(
            [
                AmbleContentCursor(user_id=first.id, entity_id="cafe"),
                AmbleContentCursor(user_id=second.id, entity_id="cafe"),
            ]
        )
        db_session.commit()

        assert db_session.query(AmbleContentCursor).filter_by(entity_id="cafe").count() == 2


class TestBindingOverride:
    def test_tuning_options_default_to_off(self, db_session, create_user):
        admin = create_user(username="admin_a", is_admin=True)
        row = AmbleBindingOverride(entity_id="cafe", binding_json=BINDING_JSON, updated_by=admin.id)
        db_session.add(row)
        db_session.commit()

        assert row.freshness_bias == 0.0
        assert row.personalise_by_follow is False
        assert row.empty_state_text is None
        assert row.binding_json == BINDING_JSON

    def test_entity_id_is_the_primary_key(self, db_session, create_user):
        admin_id = create_user(username="admin_a", is_admin=True).id
        db_session.add(
            AmbleBindingOverride(entity_id="cafe", binding_json=BINDING_JSON, updated_by=admin_id)
        )
        db_session.commit()
        db_session.expunge_all()  # so the second row is a new object, not an update

        db_session.add(
            AmbleBindingOverride(entity_id="cafe", binding_json=BINDING_JSON, updated_by=admin_id)
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
