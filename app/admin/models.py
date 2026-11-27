from enum import StrEnum

from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base

# A new report, waiting for a moderator; moderators then review or dismiss it.
REPORT_STATUS_PENDING = "pending"


class ReportTarget(StrEnum):
    """What a report is about. Exactly one of the matching id columns is set."""

    POST = "post"  # post_id (its images included)
    BLOG = "blog"  # blog_id
    PROFILE_PICTURE = "profile_picture"  # reported_user_id


class AdminAction(Base):
    """Audit log for admin actions."""

    __tablename__ = "admin_actions"

    id = Column(Integer, primary_key=True)
    admin_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    action_type = Column(String(50), nullable=False)  # ban_user, delete_post, approve_blog, etc.
    target_type = Column(String(50), nullable=False)  # user, post, blog, report
    target_id = Column(Integer, nullable=False)
    reason = Column(Text, nullable=True)
    action_metadata = Column(JSON, nullable=True)
    unix_timestamp = Column(Integer, nullable=False)


class Report(Base):
    """User-submitted reports on posts, blog posts and profile pictures."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(20), default=ReportTarget.POST.value)
    post_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("posts.id"), index=True)
    blog_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("blog_posts.id"), index=True)
    reported_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    # pending, reviewed, dismissed
    status: Mapped[str] = mapped_column(String(20), default=REPORT_STATUS_PENDING)
    unix_timestamp: Mapped[int] = mapped_column(Integer)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    reviewed_at: Mapped[int | None] = mapped_column(Integer)


class CustomGraph(Base):
    """User-created custom graph definitions (Grafana-like)."""

    __tablename__ = "custom_graphs"

    id = Column(Integer, primary_key=True)
    admin_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    graph_type = Column(String(30), nullable=False)  # line, bar, pie, scatter, area, table
    data_source = Column(String(50), nullable=False)  # posts, users, engagement, blogs, reports
    x_axis = Column(String(100), nullable=False)  # field name for x-axis
    y_axis = Column(String(100), nullable=False)  # field name or aggregation for y-axis
    filters = Column(JSON, nullable=True)  # optional filters
    group_by = Column(String(100), nullable=True)  # optional grouping
    time_range = Column(String(20), default="7d", nullable=False)  # 1d, 7d, 30d, 90d, all
    created_at = Column(Integer, nullable=False)
