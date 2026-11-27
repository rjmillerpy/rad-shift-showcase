"""reports can target blog posts and profile pictures, not only posts

Revision ID: v7r8s9t0u1v2
Revises: u6q7r8s9t0u1
Create Date: 2026-11-27 16:00:00.000000

Product roadmap Phase 2 gate: every kind of user content can be reported.
Existing rows are all post reports, so target_type starts as "post" for
them. The previous image keeps working: it only ever writes post reports
with post_id set, and target_type has a server default.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "v7r8s9t0u1v2"
down_revision: Union[str, None] = "u6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.add_column(
            sa.Column("target_type", sa.String(length=20), nullable=False, server_default="post")
        )
        batch.add_column(sa.Column("blog_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("reported_user_id", sa.Integer(), nullable=True))
        batch.alter_column("post_id", existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key("fk_reports_blog_id", "blog_posts", ["blog_id"], ["id"])
        batch.create_foreign_key("fk_reports_reported_user_id", "users", ["reported_user_id"], ["id"])
        batch.create_index("ix_reports_blog_id", ["blog_id"])
        batch.create_index("ix_reports_reported_user_id", ["reported_user_id"])


def downgrade() -> None:
    # Reports on anything but posts have no place in the old table.
    op.execute("DELETE FROM reports WHERE target_type <> 'post'")
    with op.batch_alter_table("reports") as batch:
        batch.drop_index("ix_reports_reported_user_id")
        batch.drop_index("ix_reports_blog_id")
        batch.drop_constraint("fk_reports_reported_user_id", type_="foreignkey")
        batch.drop_constraint("fk_reports_blog_id", type_="foreignkey")
        batch.alter_column("post_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("reported_user_id")
        batch.drop_column("blog_id")
        batch.drop_column("target_type")
