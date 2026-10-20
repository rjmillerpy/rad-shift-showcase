"""add platform + platform_config columns to generator_sources

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2026-05-12 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'j5e6f7g8h9i0'
down_revision: Union[str, None] = 'i4d5e6f7g8h9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'generator_sources',
        sa.Column('platform', sa.String(32), nullable=False, server_default='web'),
    )
    op.add_column(
        'generator_sources',
        sa.Column('platform_config', sa.JSON(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('generator_sources', 'platform_config')
    op.drop_column('generator_sources', 'platform')
