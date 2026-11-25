"""add widget_data (widget storage)

Revision ID: q2m3n4o5p6q7
Revises: p1l2m3n4o5p6
Create Date: 2026-11-25 16:00:00.000000

Product roadmap Phase 1, Widget Storage: sandboxed widgets have no
localStorage, so radshift.storage saves here, per user and widget. New
table only: the previous image ignores it (expand first).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q2m3n4o5p6q7"
down_revision: Union[str, None] = "p1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "widget_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("widget_id", sa.Integer(), sa.ForeignKey("widgets.id"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "widget_id", "key", name="unique_widget_data_key"),
    )
    op.create_index("ix_widget_data_user_id", "widget_data", ["user_id"])
    op.create_index("ix_widget_data_widget_id", "widget_data", ["widget_id"])


def downgrade() -> None:
    op.drop_table("widget_data")
