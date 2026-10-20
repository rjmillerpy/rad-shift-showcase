"""Follow / unfollow domain service."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, followers


def is_following(follower_id: int, followed_id: int, db: Session) -> bool:
    """True if `follower_id` currently follows `followed_id`."""
    row = db.execute(
        select(followers).where(
            followers.c.follower_id == follower_id,
            followers.c.followed_id == followed_id,
        )
    ).first()
    return row is not None


def follow_user(current_user: User, user_to_follow: User, db: Session) -> None:
    """Add `user_to_follow` to `current_user.followed` and persist."""
    current_user.followed.append(user_to_follow)
    db.commit()


def unfollow_user(current_user: User, user_to_unfollow: User, db: Session) -> None:
    """Remove `user_to_unfollow` from `current_user.followed` and persist."""
    current_user.followed.remove(user_to_unfollow)
    db.commit()
