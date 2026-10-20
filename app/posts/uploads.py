"""File-upload plumbing: allowlist checks, S3 key naming, multi-media extraction."""

import logging
import re
from typing import Any

from fastapi import UploadFile

from app.common.s3 import upload_fileobj_to_s3

from .constants import (
    ALLOWED_ARCHIVE_EXTENSIONS,
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_DOCUMENT_EXTENSIONS,
    ALLOWED_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    EXTENSION_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
)

logger = logging.getLogger(__name__)


_S3_KEY_UNSAFE = re.compile(r"[^a-zA-Z0-9._-]")
_DEFAULT_CONTENT_TYPE = "application/octet-stream"


def _sanitize_s3_key_part(value: str) -> str:
    """Strip characters that could cause path traversal or S3 key issues."""
    return _S3_KEY_UNSAFE.sub("_", value)


def _validate_upload(file: UploadFile, extension: str) -> bool:
    """Check extension allowlist and file size. Returns True if valid."""
    if extension not in ALLOWED_EXTENSIONS:
        logger.warning("Rejected upload with disallowed extension: %s", extension)
        return False

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > MAX_FILE_SIZE_BYTES:
        logger.warning(
            "Rejected upload exceeding %sMB: %s (%s bytes)",
            MAX_FILE_SIZE_MB,
            file.filename,
            file_size,
        )
        return False
    return True


def _build_s3_key(
    extension: str,
    safe_username: str,
    unix_time: int,
    counters: dict,
) -> str:
    """Build the S3 object key based on file type."""
    if extension in ALLOWED_IMAGE_EXTENSIONS:
        key = f"posts/{safe_username}_{unix_time}_{counters['img']}.{extension}"
        counters["img"] += 1
        return key
    if extension in ALLOWED_DOCUMENT_EXTENSIONS or extension in ALLOWED_ARCHIVE_EXTENSIONS:
        key = f"posts/{safe_username}_{unix_time}_doc_{counters['doc']}.{extension}"
        counters["doc"] += 1
        return key
    return f"posts/{safe_username}_{unix_time}.{extension}"


def _extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower()


def _assign_url_by_kind(
    extension: str,
    file_url: str,
    buckets: dict,
) -> None:
    """Route a single uploaded file's URL into the correct bucket by kind."""
    if extension in ALLOWED_VIDEO_EXTENSIONS:
        buckets["video_url"] = file_url
    elif extension in ALLOWED_AUDIO_EXTENSIONS:
        buckets["audio_url"] = file_url
    elif extension in ALLOWED_IMAGE_EXTENSIONS:
        buckets["image_urls"].append(file_url)
    elif extension in ALLOWED_DOCUMENT_EXTENSIONS or extension in ALLOWED_ARCHIVE_EXTENSIONS:
        buckets["document_urls"].append(file_url)


def get_multimedia_urls(request_files: dict, username: str, unix_time: int) -> dict:
    """Returns dict with image_url, image_urls, video_url, audio_url, document_urls, media_metadata."""
    # Local import breaks the media.py <-> uploads.py cycle at load time.
    from app.posts.media import extract_media_metadata

    buckets: dict[str, Any] = {
        "video_url": None,
        "audio_url": None,
        "image_urls": [],
        "document_urls": [],
    }
    media_metadata: dict | None = None
    safe_username = _sanitize_s3_key_part(username)
    counters = {"img": 0, "doc": 0}

    for _key, file in request_files.items():
        if not file or file.filename == "":
            continue
        extension = _extension_of(file.filename)
        if not _validate_upload(file, extension):
            continue

        is_media = extension in ALLOWED_AUDIO_EXTENSIONS or extension in ALLOWED_VIDEO_EXTENSIONS
        if is_media and media_metadata is None:
            media_metadata = extract_media_metadata(file.file, extension)
            file.file.seek(0)

        content_type = EXTENSION_CONTENT_TYPES.get(extension, _DEFAULT_CONTENT_TYPE)
        s3_key = _build_s3_key(extension, safe_username, unix_time, counters)
        file_url = upload_fileobj_to_s3(file.file, s3_key, content_type=content_type)
        _assign_url_by_kind(extension, file_url, buckets)

    return {
        "image_url": buckets["image_urls"][0] if buckets["image_urls"] else None,
        "image_urls": buckets["image_urls"] or None,
        "video_url": buckets["video_url"],
        "audio_url": buckets["audio_url"],
        "document_urls": buckets["document_urls"] or None,
        "media_metadata": media_metadata,
    }
