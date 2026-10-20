"""Post CRUD endpoints: create, get, replies, drafts, saved, publish.

The `/{post_id}` catch-all lives here and MUST be registered last (see
`views/__init__.py` for the include-order comment).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import optional_user, required_user, verified_user

from ..constants import MAX_POST_TEXT_CHARS
from ..feeds import (
    get_replies_formatted,
    get_saved_posts_formatted,
    get_single_post_formatted,
    get_user_drafts_formatted,
)
from ..schema import (
    DraftsResponse,
    PostCreatedResponse,
    PostStatusResponse,
    RepliesResponse,
    SavedPostsResponse,
    SinglePostResponse,
)
from ..search import get_full_metadata
from ..service import create_post, publish_draft
from ..uploads import get_multimedia_urls

router = APIRouter()


def _collect_upload_files(
    image: UploadFile | None,
    images: list[UploadFile],
    video: UploadFile | None,
    audio: UploadFile | None,
    documents: list[UploadFile],
) -> dict:
    """Fold every upload field into the single dict `get_multimedia_urls` wants."""
    files: dict = {"video": video, "audio": audio}
    if image and image.filename:
        files["image_0"] = image
    for i, img in enumerate(images):
        if img and img.filename:
            files[f"image_{i + 1}"] = img
    for i, doc in enumerate(documents):
        if doc and doc.filename:
            files[f"doc_{i}"] = doc
    return files


def _validated_metadata(text: str, post_metadata: str, db: Session) -> dict:
    """Check the text length and parse the metadata JSON, or raise 400."""
    if len(text) > MAX_POST_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Post text must be {MAX_POST_TEXT_CHARS} characters or fewer",
        )
    metadata = get_full_metadata(post_metadata, db)
    if metadata is None:
        raise HTTPException(status_code=400, detail="Invalid post metadata format")
    return metadata


def _created_response(media: dict, is_draft: bool) -> PostCreatedResponse:
    return PostCreatedResponse(
        message="Draft saved" if is_draft else "Post created",
        image_url=media["image_url"],
        image_urls=media["image_urls"],
        video_url=media["video_url"],
        audio_url=media["audio_url"],
        document_urls=media["document_urls"],
    )


@router.post("/add")
def add_post(
    text: str = Form(...),
    post_metadata: str = Form("{}"),
    image: UploadFile | None = File(None),
    images: list[UploadFile] = File(default=[]),
    video: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
    documents: list[UploadFile] = File(default=[]),
    is_draft: bool = Form(False),
    parent_post_id: int | None = Form(None),
    is_reply: bool = Form(False),
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> PostCreatedResponse:
    metadata = _validated_metadata(text, post_metadata, db)
    unix_timestamp = int(datetime.now().timestamp())
    all_files = _collect_upload_files(image, images, video, audio, documents)
    media = get_multimedia_urls(all_files, user.username, unix_timestamp)

    create_post(
        text,
        metadata,
        unix_timestamp,
        user,
        media["image_url"],
        media["video_url"],
        media["audio_url"],
        db,
        image_urls=media["image_urls"],
        document_urls=media["document_urls"],
        media_metadata=media["media_metadata"],
        parent_post_id=parent_post_id,
        is_draft=is_draft,
        is_reply=is_reply,
    )
    return _created_response(media, is_draft)


@router.post("/drafts/publish/{post_id}")
def publish_draft_view(
    post_id: int,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> PostStatusResponse:
    return PostStatusResponse.model_validate(publish_draft(post_id, user, db))


@router.get("/saved")
def get_saved(
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> SavedPostsResponse:
    posts = get_saved_posts_formatted(user, db)
    return SavedPostsResponse(posts=posts)


@router.get("/drafts")
def get_drafts(
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> DraftsResponse:
    drafts = get_user_drafts_formatted(user, db)
    return DraftsResponse(drafts=drafts)


@router.get("/{post_id}")
def get_single_post(
    post_id: int,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> SinglePostResponse:
    post = get_single_post_formatted(post_id, db=db, current_user=current_user)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return SinglePostResponse(post=post)


@router.get("/{post_id}/replies")
def get_post_replies(
    post_id: int,
    current_user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> RepliesResponse:
    replies = get_replies_formatted(
        parent_post_id=post_id,
        db=db,
        current_user=current_user,
    )
    return RepliesResponse(replies=replies)
