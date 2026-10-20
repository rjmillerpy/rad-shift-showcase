"""Business logic for the profile domain: build profile response, update bio,
upload profile picture, and the shared settings-get/set primitive used by the
four settings endpoints (algo, bubble, chronicle, agora).
"""

import logging
import re
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.s3 import upload_fileobj_to_s3

from .constants import (
    ALLOWED_PROFILE_PIC_EXTENSIONS,
    MAX_USER_POSTS_ON_PROFILE,
    PROFILE_PIC_CONTENT_TYPES,
    PROFILE_PIC_S3_KEY_PREFIX,
)
from .schema import ProfileData

logger = logging.getLogger(__name__)


_S3_KEY_UNSAFE = re.compile(r"[^a-zA-Z0-9._-]")


def _get_user_profile(
    user: User,
    current_user: User | None = None,
    db: Session | None = None,
    posts_limit: int = MAX_USER_POSTS_ON_PROFILE,
) -> dict:
    from app.posts.models import PostModel
    from app.posts.serializer import build_post_responses

    if db is None:
        db = Session.object_session(user)
    if db is None:
        raise ValueError("user is not attached to a session; pass db explicitly")

    posts = (
        db.query(PostModel)
        .filter(PostModel.user_id == user.id, PostModel.is_draft == False)  # noqa: E712
        .order_by(PostModel.unix_timestamp.desc())
        .limit(posts_limit)
        .all()
    )
    post_responses = build_post_responses(posts, current_user, db)
    return {
        "username": user.username,
        "bio": user.bio,
        "profile_picture_url": user.profile_picture_url,
        "posts": [asdict(pr) for pr in post_responses],
    }


def _update_profile(user: User, data: ProfileData, db: Session) -> None:
    """Apply the fields the client actually sent (rule 20 — don't overwrite
    unset fields with None)."""
    updates = data.model_dump(exclude_unset=True)
    if "bio" in updates:
        user.bio = updates["bio"]
    if "profile_picture_url" in updates:
        user.profile_picture_url = updates["profile_picture_url"]
    db.commit()


def _extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _upload_profile_picture(
    user: User,
    files: dict[str, UploadFile],
    db: Session,
) -> tuple[bool, str]:
    file = files.get("file")
    if not file:
        return False, "File not found"

    extension = _extension_of(file.filename or "")
    if extension not in ALLOWED_PROFILE_PIC_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_PROFILE_PIC_EXTENSIONS))
        return False, f"File type not allowed. Accepted: {allowed}"

    safe_username = _S3_KEY_UNSAFE.sub("_", user.username)
    content_type = PROFILE_PIC_CONTENT_TYPES[extension]
    timestamp = int(datetime.now(UTC).timestamp())
    s3_key = f"{PROFILE_PIC_S3_KEY_PREFIX}/{safe_username}_{timestamp}.{extension}"

    try:
        url = upload_fileobj_to_s3(file.file, s3_key, content_type=content_type)
    except Exception as exc:  # noqa: BLE001
        # S3 upload is best-effort — botocore itself can raise `BotoCoreError`
        # or `ClientError`, and the transport layer beneath it (urllib3, ssl)
        # raises its own hierarchy. Rather than enumerate every possibility,
        # collapse any upload failure into a domain-level "failed" so the
        # caller can turn it into a clean 500. `logger.error` keeps the raw
        # exception in the log for triage (rule 14 satisfied by explicit log).
        logger.error("S3 upload failed for user %s: %s", user.id, exc)
        return False, "File upload failed"

    user.profile_picture_url = url
    db.commit()
    return True, url


# ── Settings helpers ───────────────────────────────────────────────────────


def get_merged_settings(user: User, attr_name: str, defaults: dict) -> dict:
    """Return `defaults` overlaid with whatever the user has stored on
    `user.<attr_name>` — the two callers (get + put) share this shape."""
    stored = getattr(user, attr_name) or {}
    return {**defaults, **stored}


def apply_settings_update(
    user: User,
    attr_name: str,
    defaults: dict,
    payload: BaseModel,
    db: Session,
) -> dict:
    """Merge only the fields the client sent (`model_fields_set`) into the stored
    settings, then commit.

    Builds a new dict rather than mutating the stored one: the column is a
    plain JSON type, so SQLAlchemy only detects a change on reassignment.
    Mutating in place meant every save after the first was silently dropped.
    """
    provided = payload.model_dump(exclude_unset=True)
    current = {
        **(getattr(user, attr_name) or {}),
        **{key: provided[key] for key in defaults if key in provided},
    }
    setattr(user, attr_name, current)
    db.commit()
    return {**defaults, **current}
