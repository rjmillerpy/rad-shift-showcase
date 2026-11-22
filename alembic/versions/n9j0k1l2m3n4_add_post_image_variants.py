"""add posts.image_variants

Revision ID: n9j0k1l2m3n4
Revises: m8i9j0k1l2m3
Create Date: 2026-11-22 05:00:00.000000

Roadmap item 28: smaller WebP copies of each post image, recorded by the
media pipeline after upload (app/media/). Nullable: absent until the
Lambda's result arrives, and for every post made before it existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'n9j0k1l2m3n4'
down_revision: Union[str, None] = 'm8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('image_variants', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('posts', 'image_variants')
