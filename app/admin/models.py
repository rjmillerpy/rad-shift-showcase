from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Text

from app.common.db import Base


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
    """User-submitted reports on posts."""

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    reporter_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), index=True, nullable=False)
    reason = Column(String(500), nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending, reviewed, dismissed
    unix_timestamp = Column(Integer, nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(Integer, nullable=True)


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
