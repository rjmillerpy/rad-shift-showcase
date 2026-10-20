"""add amble_binding_overrides table

Revision ID: l7h8i9j0k1l2
Revises: k6f7g8h9i0j1
Create Date: 2026-07-15 04:00:00.000000

Phase 2.2a — admin-authored per-entity binding overrides that take
precedence over the versioned YAML defaults.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'l7h8i9j0k1l2'
down_revision: Union[str, None] = 'k6f7g8h9i0j1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'amble_binding_overrides',
        sa.Column('entity_id', sa.String(length=64), primary_key=True),
        sa.Column('binding_json', sa.JSON(), nullable=False),
        sa.Column('empty_state_text', sa.String(length=280), nullable=True),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('amble_binding_overrides')
