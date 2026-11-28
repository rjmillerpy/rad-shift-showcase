from enum import StrEnum

from sqlalchemy import JSON, Boolean, Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db import Base

# A content warning's label ("spoilers", "violence"), shown before the post.
# Here, not in constants.py, which imports this module.
MAX_CONTENT_WARNING_LENGTH = 100
# A post topic, lowercased, without the "#" (app/posts/topics.py).
MAX_TOPIC_LENGTH = 50


class AiLabel(StrEnum):
    """Why a post carries the "AI-generated" label."""

    AUTHOR = "author"  # the author said so when posting
    CONTENT_CREDENTIALS = "content_credentials"  # an image's own metadata said so
    MODERATOR = "moderator"  # a moderator added it (logged)


class PostModel(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    text = Column(String, nullable=False)
    unix_timestamp = Column(Integer, index=True)
    post_metadata = Column(JSON)
    user = relationship("User", back_populates="posts")
    image_url = Column(String, nullable=True)
    image_urls = Column(JSON, nullable=True)  # Array of image URLs for multi-image posts
    # {original image URL: {"480": WebP URL, "1280": ..., "<its width>": the
    # original}}, every size it's available at, filled in after upload by the
    # media pipeline (app/media/); absent until then.
    image_variants = Column(JSON, nullable=True)
    video_url = Column(String, nullable=True)
    audio_url = Column(String, nullable=True)
    document_urls = Column(JSON, nullable=True)  # Array of document/file URLs
    likes = Column(Integer, default=0)
    reposts = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    laughs = Column(Integer, default=0)
    media_metadata = Column(JSON, nullable=True)  # {duration_seconds, format, bitrate, dimensions}
    parent_post_id = Column(Integer, ForeignKey("posts.id"), nullable=True, index=True)
    is_draft = Column(Boolean, default=False, nullable=False)
    is_reply = Column(Boolean, default=False, nullable=False)
    # Shown in place of the post until the reader chooses to see it. Set by
    # the author, or by a moderator (logged as an admin action).
    content_warning = Column(String(MAX_CONTENT_WARNING_LENGTH), nullable=True)
    # Why the post is labelled AI-generated (an AiLabel value), or null.
    ai_label = Column(String(32), nullable=True)
    # When a moderator last dismissed its slop flags; earlier flags stop counting.
    slop_cleared_at = Column(Integer, nullable=True)

    parent_post = relationship(
        "PostModel",
        remote_side=[id],
        backref="quoted_children",
        foreign_keys=[parent_post_id],
    )

    __table_args__ = (Index("ix_posts_feed", "is_draft", "is_reply", "unix_timestamp"),)


class PostLike(Base):
    __tablename__ = "post_like"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), index=True)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="user_post_like_uc"),)


class Repost(Base):
    __tablename__ = "reposts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    original_post_id = Column(Integer, ForeignKey("posts.id"), index=True)
    unix_timestamp = Column(Integer)

    user = relationship("User", back_populates="reposts")


class PostShare(Base):
    __tablename__ = "post_shares"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), index=True)
    timestamp = Column(Integer)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_user_post_share"),)


class PostSave(Base):
    __tablename__ = "post_saves"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), index=True)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_user_post_save"),)


class PostLaugh(Base):
    __tablename__ = "post_laughs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), index=True)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_user_post_laugh"),)


class Slop(Base):
    __tablename__ = "slop"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), index=True, nullable=False)
    reason = Column(String, nullable=False)
    unix_timestamp = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_user_post_slop"),)


class PostTopic(Base):
    """One of a post's topics (app/posts/topics.py), for tailoring feeds."""

    __tablename__ = "post_topics"

    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    topic: Mapped[str] = mapped_column(String(MAX_TOPIC_LENGTH), primary_key=True, index=True)
