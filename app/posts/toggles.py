import logging
import time

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import User

from .models import PostLaugh, PostLike, PostModel, PostSave, PostShare, Repost, Slop

logger = logging.getLogger(__name__)


def _get_post_or_404(post_id: int, db: Session) -> PostModel:
    post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def toggle_like(post_id: int, user: User, db: Session) -> dict:
    post = _get_post_or_404(post_id, db)

    existing_like = db.query(PostLike).filter_by(post_id=post_id, user_id=user.id).first()

    if existing_like:
        db.delete(existing_like)
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(likes=func.greatest(func.coalesce(PostModel.likes, 0) - 1, 0))
        )
        action = "unliked"
    else:
        db.add(PostLike(post_id=post_id, user_id=user.id))
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(likes=func.coalesce(PostModel.likes, 0) + 1)
        )
        action = "liked"

    db.commit()
    db.refresh(post)
    return {"likes": post.likes, "action": action}


def toggle_laugh(post_id: int, user: User, db: Session) -> dict:
    post = _get_post_or_404(post_id, db)

    existing = db.query(PostLaugh).filter_by(post_id=post_id, user_id=user.id).first()

    if existing:
        db.delete(existing)
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(laughs=func.greatest(func.coalesce(PostModel.laughs, 0) - 1, 0))
        )
        action = "unlaughed"
    else:
        db.add(PostLaugh(post_id=post_id, user_id=user.id))
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(laughs=func.coalesce(PostModel.laughs, 0) + 1)
        )
        action = "laughed"

    db.commit()
    db.refresh(post)
    return {"laughs": post.laughs, "action": action}


def toggle_repost(post_id: int, user: User, db: Session) -> dict:
    post = _get_post_or_404(post_id, db)

    existing_repost = db.query(Repost).filter_by(user_id=user.id, original_post_id=post_id).first()

    if existing_repost:
        db.delete(existing_repost)
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(reposts=func.greatest(func.coalesce(PostModel.reposts, 0) - 1, 0))
        )
        action = "un-re-posted"
    else:
        db.add(Repost(user_id=user.id, original_post_id=post_id))
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(reposts=func.coalesce(PostModel.reposts, 0) + 1)
        )
        action = "re-posted"

    db.commit()
    db.refresh(post)
    return {"reposts": post.reposts, "action": action}


def toggle_save(post_id: int, user: User, db: Session) -> dict:
    post = _get_post_or_404(post_id, db)

    existing = db.query(PostSave).filter_by(user_id=user.id, post_id=post_id).first()
    if existing:
        db.delete(existing)
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(saves=func.greatest(func.coalesce(PostModel.saves, 0) - 1, 0))
        )
        action = "unsaved"
    else:
        db.add(PostSave(user_id=user.id, post_id=post_id))
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(saves=func.coalesce(PostModel.saves, 0) + 1)
        )
        action = "saved"

    db.commit()
    db.refresh(post)
    return {"saves": post.saves, "action": action}


def share_post(post_id: int, user: User | None, db: Session) -> dict:
    post = _get_post_or_404(post_id, db)

    try:
        db.execute(
            PostModel.__table__.update()
            .where(PostModel.id == post_id)
            .values(shares=func.coalesce(PostModel.shares, 0) + 1)
        )
        if user is not None:
            new_share = PostShare(user_id=user.id, post_id=post_id, timestamp=int(time.time()))
            db.add(new_share)
        db.commit()
        db.refresh(post)
    except IntegrityError as exc:
        db.rollback()
        if "unique_user_post_share" in str(exc.orig):
            # Duplicate share by an authenticated user — bumping the counter
            # again would double-count, so we skip and log for observability.
            user_id = user.id if user is not None else None
            logger.info(
                "User %s already shared post %d; duplicate ignored.",
                user_id,
                post_id,
            )
        else:
            raise HTTPException(status_code=500, detail="Unexpected database error.") from exc

    return {"share_url": f"/post/{post_id}", "shares": post.shares}


def mark_post_slop(post_id: int, user: User, reason: str, db: Session) -> dict:
    _get_post_or_404(post_id, db)

    existing = db.query(Slop).filter_by(user_id=user.id, post_id=post_id).first()
    if existing:
        existing.reason = reason
        db.commit()
        return {"status": "updated", "post_id": post_id}

    sm = Slop(
        user_id=user.id,
        post_id=post_id,
        reason=reason,
        unix_timestamp=int(time.time()),
    )
    db.add(sm)
    db.commit()
    return {"status": "ok", "post_id": post_id}
