"""add widget_likes, widget_saves and widget_reports

Revision ID: p1l2m3n4o5p6
Revises: o0k1l2m3n4o5
Create Date: 2026-11-25 14:00:00.000000

Product roadmap Phase 1: the widget store's like, save and report buttons
called endpoints that didn't exist. Per-user rows make liking and saving
idempotent; reports send a widget back to review. New tables only: the
previous image ignores them (expand first).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p1l2m3n4o5p6"
down_revision: Union[str, None] = "o0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _per_user_table(name: str, constraint: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("widget_id", sa.Integer(), sa.ForeignKey("widgets.id"), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "widget_id", name=constraint),
    )
    op.create_index(f"ix_{name}_user_id", name, ["user_id"])
    op.create_index(f"ix_{name}_widget_id", name, ["widget_id"])


def upgrade() -> None:
    _per_user_table("widget_likes", "unique_widget_like")
    _per_user_table("widget_saves", "unique_widget_save")
    op.create_table(
        "widget_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reporter_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("widget_id", sa.Integer(), sa.ForeignKey("widgets.id"), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("reporter_user_id", "widget_id", name="unique_widget_report"),
    )
    op.create_index("ix_widget_reports_reporter_user_id", "widget_reports", ["reporter_user_id"])
    op.create_index("ix_widget_reports_widget_id", "widget_reports", ["widget_id"])


def downgrade() -> None:
    op.drop_table("widget_reports")
    op.drop_table("widget_saves")
    op.drop_table("widget_likes")
