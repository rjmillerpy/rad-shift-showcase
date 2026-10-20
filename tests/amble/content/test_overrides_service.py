"""Tests for app/amble/content/overrides_service.py — real rows, no mocks."""

import pytest

from app.amble.content import overrides_service
from app.amble.content.schema import CategoryBinding, PersistentIdentityBinding


@pytest.fixture()
def admin(create_user):
    return create_user(username="binding_admin", is_admin=True)


def _category(*tags: str) -> CategoryBinding:
    return CategoryBinding(kind="category", tags=list(tags))


class TestUpsert:
    def test_inserts_a_new_override(self, db_session, admin):
        row = overrides_service.upsert_override(db_session, "cafe", _category("coffee"), admin.id)

        assert row.entity_id == "cafe"
        assert row.binding_json == {"kind": "category", "tags": ["coffee"], "weight": 1.0}
        assert row.updated_by == admin.id
        assert (row.freshness_bias, row.personalise_by_follow) == (0.0, False)

    def test_replaces_every_field_of_an_existing_override(self, db_session, admin, create_user):
        other_admin = create_user(username="second_admin", is_admin=True)
        overrides_service.upsert_override(
            db_session, "cafe", _category("coffee"), admin.id, empty_state_text="Quiet today"
        )

        replacement = PersistentIdentityBinding(kind="persistent-identity", usernames=["barista"])
        row = overrides_service.upsert_override(
            db_session,
            "cafe",
            replacement,
            other_admin.id,
            freshness_bias=0.7,
            personalise_by_follow=True,
        )

        assert row.binding_json["kind"] == "persistent-identity"
        assert row.empty_state_text is None  # not carried over from the old row
        assert (row.freshness_bias, row.personalise_by_follow) == (0.7, True)
        assert row.updated_by == other_admin.id
        assert len(overrides_service.list_all_overrides(db_session)) == 1


class TestRead:
    def test_get_returns_none_when_absent(self, db_session):
        assert overrides_service.get_override(db_session, "nowhere") is None

    def test_get_returns_the_stored_row(self, db_session, admin):
        overrides_service.upsert_override(db_session, "cafe", _category("coffee"), admin.id)
        assert overrides_service.get_override(db_session, "cafe").entity_id == "cafe"

    def test_list_is_sorted_by_entity_id(self, db_session, admin):
        for entity_id in ("park", "bakery", "cafe"):
            overrides_service.upsert_override(db_session, entity_id, _category("x"), admin.id)

        listed = [row.entity_id for row in overrides_service.list_all_overrides(db_session)]
        assert listed == ["bakery", "cafe", "park"]

    def test_list_is_empty_without_overrides(self, db_session):
        assert overrides_service.list_all_overrides(db_session) == []


class TestDelete:
    def test_removes_the_row_and_reports_it(self, db_session, admin):
        overrides_service.upsert_override(db_session, "cafe", _category("coffee"), admin.id)

        assert overrides_service.delete_override(db_session, "cafe") is True
        assert overrides_service.get_override(db_session, "cafe") is None

    def test_is_idempotent(self, db_session):
        assert overrides_service.delete_override(db_session, "never-existed") is False
