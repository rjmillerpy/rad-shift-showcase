"""add analytics_events and analytics_salts

Revision ID: w8s9t0u1v2w3
Revises: v7r8s9t0u1v2
Create Date: 2026-11-27 18:00:00.000000

Product roadmap Phase 3: first-party, cookieless analytics (app/web_analytics/).
New tables only, so the previous image is unaffected.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w8s9t0u1v2w3"
down_revision: Union[str, None] = "v7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.Integer(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("visitor", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("path", sa.String(length=200), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=True),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=True),
    )
    op.create_index("ix_analytics_events_day_type", "analytics_events", ["day", "event_type"])
    op.create_index("ix_analytics_events_mode", "analytics_events", ["mode"])
    op.create_table(
        "analytics_salts",
        sa.Column("day", sa.Integer(), primary_key=True),
        sa.Column("salt", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("analytics_salts")
    op.drop_index("ix_analytics_events_mode", table_name="analytics_events")
    op.drop_index("ix_analytics_events_day_type", table_name="analytics_events")
    op.drop_table("analytics_events")
