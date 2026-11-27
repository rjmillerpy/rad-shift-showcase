"""add community_notes and community_note_ratings

Revision ID: t5p6q7r8s9t0
Revises: s4o5p6q7r8s9
Create Date: 2026-11-27 12:00:00.000000

Product roadmap Phase 2: community notes, shown on a post once raters who
usually disagree both find them helpful (app/community_notes/scoring.py).
New tables only, so the previous image is unaffected (expand first).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t5p6q7r8s9t0"
down_revision: Union[str, None] = "s4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "community_notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("intercept", sa.Float(), nullable=True),
        sa.Column("factor", sa.Float(), nullable=True),
        sa.Column("is_removed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("post_id", "author_id"),
    )
    op.create_index("ix_community_notes_post_id", "community_notes", ["post_id"])
    op.create_index("ix_community_notes_author_id", "community_notes", ["author_id"])
    op.create_index("ix_community_notes_status", "community_notes", ["status"])
    op.create_table(
        "community_note_ratings",
        sa.Column(
            "note_id",
            sa.Integer(),
            sa.ForeignKey("community_notes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("rater_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("rated_at", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("community_note_ratings")
    op.drop_index("ix_community_notes_status", table_name="community_notes")
    op.drop_index("ix_community_notes_author_id", table_name="community_notes")
    op.drop_index("ix_community_notes_post_id", table_name="community_notes")
    op.drop_table("community_notes")
