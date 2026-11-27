"""add posts.content_warning

Revision ID: s4o5p6q7r8s9
Revises: r3n4o5p6q7r8
Create Date: 2026-11-25 20:00:00.000000

Product roadmap Phase 2: a content warning shown in place of a post until
the reader chooses to see it. A nullable column: the previous image
ignores it (expand first).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s4o5p6q7r8s9"
down_revision: Union[str, None] = "r3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("content_warning", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "content_warning")
