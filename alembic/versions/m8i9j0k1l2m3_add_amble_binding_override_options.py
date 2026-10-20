"""add freshness_bias + personalise_by_follow to amble_binding_overrides

Revision ID: m8i9j0k1l2m3
Revises: l7h8i9j0k1l2
Create Date: 2026-07-15 05:00:00.000000

Phase 2.3b/c — the override table gains per-entity feed-tuning options
so admins can flip a newsstand to time-decay or turn on follow-boost
without editing the YAML.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm8i9j0k1l2m3'
down_revision: Union[str, None] = 'l7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'amble_binding_overrides',
        sa.Column('freshness_bias', sa.Float(), nullable=False, server_default='0.0'),
    )
    op.add_column(
        'amble_binding_overrides',
        sa.Column('personalise_by_follow', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('amble_binding_overrides', 'personalise_by_follow')
    op.drop_column('amble_binding_overrides', 'freshness_bias')
