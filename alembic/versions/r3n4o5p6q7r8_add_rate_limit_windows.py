"""add rate_limit_windows

Revision ID: r3n4o5p6q7r8
Revises: q2m3n4o5p6q7
Create Date: 2026-11-25 18:00:00.000000

Product roadmap Phase 2: rate limits on writes and sign-in, counted in
Postgres so every API replica shares them (app/ratelimit/). New table only:
the previous image ignores it (expand first).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "r3n4o5p6q7r8"
down_revision: Union[str, None] = "q2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_windows",
        sa.Column("key", sa.String(length=200), primary_key=True),
        sa.Column("window_start", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_rate_limit_windows_window_start", "rate_limit_windows", ["window_start"])


def downgrade() -> None:
    op.drop_table("rate_limit_windows")
