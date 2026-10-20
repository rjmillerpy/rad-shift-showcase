"""add laughs column and post_laughs table

Revision ID: f1a2b3c4d5e6
Revises: ec28f64c71a8
Create Date: 2026-03-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'ec28f64c71a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('laughs', sa.Integer(), server_default='0', nullable=True))

    op.create_table(
        'post_laughs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('posts.id'), nullable=True),
        sa.UniqueConstraint('user_id', 'post_id', name='unique_user_post_laugh'),
    )
    op.create_index('ix_post_laughs_user_id', 'post_laughs', ['user_id'])
    op.create_index('ix_post_laughs_post_id', 'post_laughs', ['post_id'])


def downgrade() -> None:
    op.drop_index('ix_post_laughs_post_id', table_name='post_laughs')
    op.drop_index('ix_post_laughs_user_id', table_name='post_laughs')
    op.drop_table('post_laughs')
    op.drop_column('posts', 'laughs')
