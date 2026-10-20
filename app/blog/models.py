from sqlalchemy import JSON, Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.common.db import Base


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    content_html = Column(Text, nullable=False)
    content_text = Column(Text, nullable=True)
    featured_image_url = Column(String, nullable=True)
    seo_title = Column(String(255), nullable=True)
    seo_description = Column(String(500), nullable=True)
    tags = Column(JSON, nullable=True)
    category = Column(String(100), nullable=True)

    # Open Graph
    og_title = Column(String(255), nullable=True)
    og_description = Column(String(500), nullable=True)
    og_image = Column(String, nullable=True)

    # Monetization
    monetized = Column(Boolean, default=False, nullable=False)
    ad_placement = Column(String(20), default="none", nullable=False)

    # Publishing
    is_draft = Column(Boolean, default=True, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    published_at = Column(Integer, nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=True)

    # Stats
    reading_time_minutes = Column(Integer, default=1, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)

    user = relationship("User", backref="blog_posts")


class BlogView(Base):
    __tablename__ = "blog_views"

    id = Column(Integer, primary_key=True)
    blog_post_id = Column(Integer, ForeignKey("blog_posts.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    view_timestamp = Column(Integer, nullable=False)
    read_time_seconds = Column(Integer, default=0, nullable=False)
    ip_hash = Column(String(64), nullable=True)
