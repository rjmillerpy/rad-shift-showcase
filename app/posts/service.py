"""Post CRUD — create, fetch by id, publish a draft.

The rest of the pre-refactor `service.py` monolith is now split across:
    * `feeds.py`      — all list/feed queries + `AlgoWeights`
    * `search.py`     — search + tag extraction
    * `serializer.py` — batch `PostResponse` construction
    * `uploads.py`    — S3 upload plumbing
    * `constants.py`  — extension allowlists, size caps, media-type dispatch
"""

import logging
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User

from .models import PostModel

logger = logging.getLogger(__name__)


def create_post(
    text: str,
    post_metadata: str,
    unix_timestamp: int,
    user: User,
    image_url: str | None,
    video_url: str | None,
    audio_url: str | None,
    db: Session,
    *,
    image_urls: list[str] | None = None,
    document_urls: list[str] | None = None,
    media_metadata: dict | None = None,
    parent_post_id: int | None = None,
    is_draft: bool = False,
    is_reply: bool = False,
) -> None:
    new_post = PostModel(
        text=text,
        post_metadata=post_metadata,
        unix_timestamp=unix_timestamp,
        user=user,
        image_url=image_url,
        image_urls=image_urls or None,
        video_url=video_url,
        audio_url=audio_url,
        document_urls=document_urls or None,
        media_metadata=media_metadata,
        parent_post_id=parent_post_id,
        is_draft=is_draft,
        is_reply=is_reply,
    )
    db.add(new_post)
    db.commit()


def get_post_by_post_id(post_id: int, db: Session) -> PostModel | None:
    return db.query(PostModel).filter(PostModel.id == post_id).first()


def publish_draft(post_id: int, user: User, db: Session) -> dict:
    post = get_post_by_post_id(post_id, db)
    if not post or post.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    if not post.is_draft:
        raise HTTPException(status_code=400, detail="Post is already published")
    post.is_draft = False
    post.unix_timestamp = int(time.time())
    db.commit()
    return {"status": "published", "post_id": post_id}
