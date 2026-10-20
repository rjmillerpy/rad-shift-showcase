"""Tests for app/widgets/templates.py — builtin template seeding."""

from app.widgets.models import WidgetTemplate
from app.widgets.templates import BUILTIN_TEMPLATES, seed_templates


class TestBuiltinTemplates:
    def test_builtin_list_is_non_empty(self):
        assert len(BUILTIN_TEMPLATES) >= 10

    def test_every_builtin_has_required_fields(self):
        required = {"name", "category", "language", "description", "starter_code"}
        for t in BUILTIN_TEMPLATES:
            missing = required - set(t.keys())
            assert not missing, f"template {t.get('name')!r} missing {missing}"


class TestSeedTemplates:
    def test_seeds_all_on_empty_db(self, db_session):
        added = seed_templates(db_session)
        assert added == len(BUILTIN_TEMPLATES)
        assert db_session.query(WidgetTemplate).count() == len(BUILTIN_TEMPLATES)

    def test_seeding_is_idempotent(self, db_session):
        first = seed_templates(db_session)
        second = seed_templates(db_session)
        assert first == len(BUILTIN_TEMPLATES)
        assert second == 0
        assert db_session.query(WidgetTemplate).count() == len(BUILTIN_TEMPLATES)
