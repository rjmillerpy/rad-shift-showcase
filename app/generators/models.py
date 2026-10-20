"""Models for the AI content generator / scraper system.

Admin-only infrastructure — no public-facing exposure.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.common.db import Base
from app.generators.constants import RunStatus


class GeneratorSource(Base):
    """Configuration for a content source to scrape."""

    __tablename__ = "generator_sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    site_url = Column(String(2000), nullable=False)
    description = Column(Text, nullable=True)

    # Which source-type this row is: "web", "reddit", "pinterest", etc.
    platform = Column(String(32), nullable=False, default="web")
    # AI-generated CSS selectors — only used when platform == "web"
    selectors = Column(JSON, nullable=True)
    # Scraping preferences shared across platforms (filters, limits)
    config = Column(JSON, nullable=False, default=dict)
    # Platform-specific config (e.g. subreddit name, sort) — shape owned by the adapter
    platform_config = Column(JSON, nullable=False, default=dict)

    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    total_posts_created = Column(Integer, default=0, nullable=False)
    consecutive_failures = Column(Integer, default=0, nullable=False)

    # Schedule: interval in minutes (0 = manual only)
    run_interval_minutes = Column(Integer, default=0, nullable=False)

    profiles = relationship(
        "GeneratorProfile", back_populates="source", cascade="all, delete-orphan"
    )
    runs = relationship("GeneratorRun", back_populates="source", cascade="all, delete-orphan")


class GeneratorProfile(Base):
    """Links a bot User account to a generator source for auto-posting."""

    __tablename__ = "generator_profiles"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("generator_sources.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    source = relationship("GeneratorSource", back_populates="profiles")
    user = relationship("User")

    __table_args__ = (Index("ix_gen_profile_source_user", "source_id", "user_id", unique=True),)


class GeneratorRun(Base):
    """Log of each scraper execution."""

    __tablename__ = "generator_runs"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("generator_sources.id"), index=True, nullable=False)
    started_at = Column(Integer, nullable=False)
    finished_at = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default=RunStatus.RUNNING.value)
    items_found = Column(Integer, default=0, nullable=False)
    items_posted = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    selectors_updated = Column(Boolean, default=False, nullable=False)

    source = relationship("GeneratorSource", back_populates="runs")
