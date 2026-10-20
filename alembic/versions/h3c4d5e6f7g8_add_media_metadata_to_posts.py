"""add media_metadata column to posts

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-04-15 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'h3c4d5e6f7g8'
down_revision: Union[str, None] = 'beeea1053068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('media_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('posts', 'media_metadata')
