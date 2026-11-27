"""add posts.ai_label

Revision ID: u6q7r8s9t0u1
Revises: t5p6q7r8s9t0
Create Date: 2026-11-27 14:00:00.000000

Product roadmap Phase 2, AI content detection: why a post is labelled
AI-generated (the author said so, an image's content credentials said so,
or a moderator). A nullable column: the previous image ignores it.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u6q7r8s9t0u1"
down_revision: Union[str, None] = "t5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("ai_label", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "ai_label")
