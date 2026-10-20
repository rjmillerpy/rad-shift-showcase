"""Blog view tracking and analytics."""

import time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.blog.models import BlogPost, BlogView


def record_blog_view(
    blog_post_id: int,
    db: Session,
    *,
    user_id: int | None = None,
    read_time_seconds: int = 0,
    ip_hash: str | None = None,
) -> None:
    """Record a view of a blog post and increment the counter."""
    view = BlogView(
        blog_post_id=blog_post_id,
        user_id=user_id,
        view_timestamp=int(time.time()),
        read_time_seconds=read_time_seconds,
        ip_hash=ip_hash,
    )
    db.add(view)
    db.query(BlogPost).filter_by(id=blog_post_id).update(
        {BlogPost.view_count: BlogPost.view_count + 1}
    )
    db.commit()


def get_blog_stats(blog_post_id: int, db: Session) -> dict:
    """Aggregate view stats for a blog post. Returns {} when the post is gone."""
    post = db.query(BlogPost).filter_by(id=blog_post_id).first()
    if not post:
        return {}

    total_read_time = (
        db.query(func.sum(BlogView.read_time_seconds)).filter_by(blog_post_id=blog_post_id).scalar()
        or 0
    )
    unique_readers = (
        db.query(func.count(func.distinct(BlogView.user_id)))
        .filter(
            BlogView.blog_post_id == blog_post_id,
            BlogView.user_id.isnot(None),
        )
        .scalar()
        or 0
    )
    return {
        "view_count": post.view_count,
        "total_read_time_seconds": total_read_time,
        "unique_readers": unique_readers,
        "reading_time_minutes": post.reading_time_minutes,
    }
