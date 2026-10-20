"""Widget system models."""

from sqlalchemy import JSON, Boolean, Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.common.db import Base


class Widget(Base):
    """A user-submitted widget (game, tool, API connector, display modifier, etc.)."""

    __tablename__ = "widgets"

    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(
        String(50), nullable=False
    )  # game, tool, api_connector, display_modifier, lambda, visualization, social
    language = Column(
        String(30), nullable=False
    )  # html, javascript, typescript, python, react, vue, svelte, rust_wasm, go_wasm

    # Code storage — multi-panel (JSFiddle-style)
    code = Column(Text, nullable=False)  # JS/logic panel content
    html_panel = Column(Text, nullable=True)  # HTML panel content
    css_panel = Column(Text, nullable=True)  # CSS panel content
    compute_panel = Column(Text, nullable=True)  # Optional Python/SQL compute panel
    compute_language = Column(String(30), nullable=True)  # Language for compute panel (python, sql)
    execution_mode = Column(String(20), default="client", nullable=False)  # "client" or "server"

    html_output = Column(Text, nullable=True)  # Compiled/combined HTML for iframe rendering
    css = Column(Text, nullable=True)  # Combined CSS (backwards compat)
    config = Column(
        JSON, nullable=True
    )  # Widget configuration (API keys needed, permissions, etc.)

    # Metadata
    version = Column(String(20), default="1.0.0", nullable=False)
    icon_emoji = Column(String(10), nullable=True)  # Display emoji icon
    thumbnail_url = Column(String, nullable=True)
    tags = Column(JSON, nullable=True)  # ["game", "puzzle", "multiplayer"]

    # Review pipeline
    status = Column(
        String(20), default="draft", nullable=False
    )  # draft, submitted, under_review, approved, rejected, suspended
    review_notes = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(Integer, nullable=True)

    # Security scan results
    security_score = Column(Integer, nullable=True)  # 0-100
    security_issues = Column(JSON, nullable=True)  # List of detected issues
    scan_passed = Column(Boolean, nullable=True)

    # Engagement (denormalized for feed display)
    install_count = Column(Integer, default=0, nullable=False)
    likes = Column(Integer, default=0, nullable=False)
    saves = Column(Integer, default=0, nullable=False)
    shares = Column(Integer, default=0, nullable=False)

    # Permissions the widget requests
    permissions = Column(
        JSON, nullable=True
    )  # ["camera", "microphone", "geolocation", "clipboard", "notifications"]

    # Display settings
    default_width = Column(Integer, default=400, nullable=False)  # pixels
    default_height = Column(Integer, default=300, nullable=False)
    resizable = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=True)
    published_at = Column(Integer, nullable=True)

    author = relationship("User", foreign_keys=[author_id], backref="widgets")

    __table_args__ = (Index("ix_widgets_status_category", "status", "category"),)


class WidgetInstall(Base):
    """Tracks which users have installed/saved a widget."""

    __tablename__ = "widget_installs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    widget_id = Column(Integer, ForeignKey("widgets.id"), index=True, nullable=False)
    installed_at = Column(Integer, nullable=False)

    from sqlalchemy import UniqueConstraint

    __table_args__ = (UniqueConstraint("user_id", "widget_id", name="unique_widget_install"),)


class WidgetReview(Base):
    """Review/rating of a widget by a user."""

    __tablename__ = "widget_reviews"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    widget_id = Column(Integer, ForeignKey("widgets.id"), index=True, nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=False)

    from sqlalchemy import UniqueConstraint

    __table_args__ = (UniqueConstraint("user_id", "widget_id", name="unique_widget_review"),)


class WidgetTemplate(Base):
    """Starter templates for common widget types."""

    __tablename__ = "widget_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    language = Column(String(30), nullable=False)
    description = Column(Text, nullable=True)
    starter_code = Column(Text, nullable=False)
    starter_css = Column(Text, nullable=True)
    starter_config = Column(JSON, nullable=True)
    icon_emoji = Column(String(10), nullable=True)
