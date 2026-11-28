"""add post_topics

Revision ID: y0v1w2x3y4z5
Revises: x9t0u1v2w3x4
Create Date: 2026-11-28 12:00:00.000000

Product roadmap Phase 3, tailored content: each post's topics (its tags and
hashtags, app/posts/topics.py), filled in here for the posts that exist.
A new table: the previous image ignores it. The backfill imports topics_of
on purpose, so existing posts get exactly the topics a new post would.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.posts.topics import topics_of


revision: str = "y0v1w2x3y4z5"
down_revision: Union[str, None] = "x9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAX_TOPIC_LENGTH = 50
_BACKFILL_BATCH = 1000


def upgrade() -> None:
    post_topics = op.create_table(
        "post_topics",
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=MAX_TOPIC_LENGTH), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("post_id", "topic"),
    )
    op.create_index("ix_post_topics_topic", "post_topics", ["topic"])

    posts = op.get_bind().execute(sa.text("SELECT id, text, post_metadata FROM posts"))
    rows = []
    for post_id, text, raw_meta in posts:
        rows.extend({"post_id": post_id, "topic": t} for t in topics_of(text, raw_meta))
        if len(rows) >= _BACKFILL_BATCH:
            op.bulk_insert(post_topics, rows)
            rows = []
    if rows:
        op.bulk_insert(post_topics, rows)


def downgrade() -> None:
    op.drop_index("ix_post_topics_topic", table_name="post_topics")
    op.drop_table("post_topics")
