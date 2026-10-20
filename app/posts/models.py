from sqlalchemy import JSON, Boolean, Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.common.db import Base


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
