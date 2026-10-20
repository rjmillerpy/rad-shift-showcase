"""merge_heads

Revision ID: 802c334fbd1e
Revises: de7507686abf, g2b3c4d5e6f7
Create Date: 2026-04-09 04:41:34.678149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '802c334fbd1e'
down_revision: Union[str, None] = ('de7507686abf', 'g2b3c4d5e6f7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
