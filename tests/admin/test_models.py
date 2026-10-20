"""Tests for app/admin/models.py — AdminAction / Report / CustomGraph ORM."""

import time

from app.admin.models import AdminAction, CustomGraph, Report


class TestAdminAction:
    def test_inserts_with_metadata(self, db_session, create_user):
        admin = create_user(username="adm", is_admin=True)
        db_session.add(
            AdminAction(
                admin_user_id=admin.id,
                action_type="ban_user",
                target_type="user",
                target_id=999,
                reason="spam",
                action_metadata={"spam_score": 0.95},
                unix_timestamp=int(time.time()),
            )
        )
        db_session.commit()

        action = db_session.query(AdminAction).one()
        assert action.action_type == "ban_user"
        assert action.action_metadata == {"spam_score": 0.95}


class TestReport:
    def test_default_status_pending(self, db_session, create_user, create_post):
        user = create_user(username="reporter")
        post = create_post(user, text="reported post")
        db_session.add(
            Report(
                reporter_user_id=user.id,
                post_id=post.id,
                reason="off-topic",
                unix_timestamp=int(time.time()),
            )
        )
        db_session.commit()

        report = db_session.query(Report).one()
        assert report.status == "pending"
        assert report.reviewed_by is None


class TestCustomGraph:
    def test_defaults_and_optional_json(self, db_session, create_user):
        admin = create_user(username="dashboard_admin", is_admin=True)
        db_session.add(
            CustomGraph(
                admin_user_id=admin.id,
                title="Daily Signups",
                graph_type="line",
                data_source="users",
                x_axis="created_at",
                y_axis="count",
                filters={"is_banned": False},
                created_at=int(time.time()),
            )
        )
        db_session.commit()

        graph = db_session.query(CustomGraph).one()
        assert graph.time_range == "7d"
        assert graph.filters == {"is_banned": False}
        assert graph.group_by is None
