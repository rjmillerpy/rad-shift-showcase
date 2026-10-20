"""add algo_settings and bubble_settings columns to users

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-27 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'g2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('algo_settings', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('bubble_settings', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'bubble_settings')
    op.drop_column('users', 'algo_settings')
