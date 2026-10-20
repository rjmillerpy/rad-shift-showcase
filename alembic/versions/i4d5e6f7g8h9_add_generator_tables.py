"""add generator tables for content scraping

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2026-04-15 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'i4d5e6f7g8h9'
down_revision: Union[str, None] = 'h3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'generator_sources',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('site_url', sa.String(2000), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('selectors', sa.JSON(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_run_at', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('total_posts_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('run_interval_minutes', sa.Integer(), nullable=False, server_default='0'),
    )

    op.create_table(
        'generator_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('generator_sources.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.create_index('ix_gen_profile_source_user', 'generator_profiles', ['source_id', 'user_id'], unique=True)
    op.create_index('ix_generator_profiles_source_id', 'generator_profiles', ['source_id'])
    op.create_index('ix_generator_profiles_user_id', 'generator_profiles', ['user_id'])

    op.create_table(
        'generator_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('generator_sources.id'), nullable=False),
        sa.Column('started_at', sa.Integer(), nullable=False),
        sa.Column('finished_at', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('items_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('items_posted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('selectors_updated', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_generator_runs_source_id', 'generator_runs', ['source_id'])


def downgrade() -> None:
    op.drop_table('generator_runs')
    op.drop_table('generator_profiles')
    op.drop_table('generator_sources')
