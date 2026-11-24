"""add post_trending and processed_post_events

Revision ID: o0k1l2m3n4o5
Revises: n9j0k1l2m3n4
Create Date: 2026-11-24 08:00:00.000000

Roadmap item 29b: the engagement aggregator (app/engagement/) keeps a
time-decayed trending score per post, fed by Kafka, and remembers which
events it applied so a redelivered one changes nothing. New tables only:
the previous image ignores them (expand first).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o0k1l2m3n4o5"
down_revision: Union[str, None] = "n9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "post_trending",
        sa.Column(
            "post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_post_trending_updated_at", "post_trending", ["updated_at"])
    op.create_table(
        "processed_post_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("processed_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_processed_post_events_processed_at", "processed_post_events", ["processed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_processed_post_events_processed_at", table_name="processed_post_events")
    op.drop_table("processed_post_events")
    op.drop_index("ix_post_trending_updated_at", table_name="post_trending")
    op.drop_table("post_trending")
