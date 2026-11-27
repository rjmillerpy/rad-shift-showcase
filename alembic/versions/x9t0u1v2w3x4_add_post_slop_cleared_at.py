"""add posts.slop_cleared_at

Revision ID: x9t0u1v2w3x4
Revises: w8s9t0u1v2w3
Create Date: 2026-11-27 20:00:00.000000

Product roadmap Phase 3, slop ranking: when a moderator dismissed a post's
slop flags; flags from before it stop counting (app/posts/slop.py).
A nullable column: the previous image ignores it.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "x9t0u1v2w3x4"
down_revision: Union[str, None] = "w8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("slop_cleared_at", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "slop_cleared_at")
