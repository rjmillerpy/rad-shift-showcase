"""Shared constants for the posts domain.

Media allowlists live here rather than in service.py so upload/metadata code
paths can import them without pulling the full service module (which was the
inverted-dependency bug documented at rule 16).
"""

from .models import PostModel

MAX_TAG_RESULTS = 100

# File-upload caps
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Text caps
MAX_POST_TEXT_CHARS = 5000

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "svg",
    "bmp",
    "tiff",
    "tif",
    "ico",
    "heic",
    "heif",
    "avif",
}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "webm", "mkv", "flv", "wmv", "m4v"}
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "aac", "m4a", "flac", "wma", "opus"}
ALLOWED_DOCUMENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "rtf",
    "odt",
    "csv",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "md",
}
ALLOWED_ARCHIVE_EXTENSIONS = {"zip", "tar", "gz", "7z", "rar"}
ALLOWED_EXTENSIONS = (
    ALLOWED_IMAGE_EXTENSIONS
    | ALLOWED_VIDEO_EXTENSIONS
    | ALLOWED_AUDIO_EXTENSIONS
    | ALLOWED_DOCUMENT_EXTENSIONS
    | ALLOWED_ARCHIVE_EXTENSIONS
)

EXTENSION_CONTENT_TYPES: dict[str, str] = {
    # Images
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "ico": "image/x-icon",
    "heic": "image/heic",
    "heif": "image/heif",
    "avif": "image/avif",
    # Video
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "avi": "video/x-msvideo",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
    "flv": "video/x-flv",
    "wmv": "video/x-ms-wmv",
    "m4v": "video/x-m4v",
    # Audio
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "aac": "audio/aac",
    "m4a": "audio/mp4",
    "flac": "audio/flac",
    "wma": "audio/x-ms-wma",
    "opus": "audio/opus",
    # Documents
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "rtf": "application/rtf",
    "odt": "application/vnd.oasis.opendocument.text",
    "csv": "text/csv",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "md": "text/markdown",
    # Archives
    "zip": "application/zip",
    "tar": "application/x-tar",
    "gz": "application/gzip",
    "7z": "application/x-7z-compressed",
    "rar": "application/vnd.rar",
}


# Feed query dispatchers — keyed on the client-visible media-type token.
MEDIA_TYPE_FILTERS = {
    "audio": lambda q: q.filter(PostModel.audio_url.isnot(None)),
    "video": lambda q: q.filter(PostModel.video_url.isnot(None)),
    "all": lambda q: q.filter(
        (PostModel.audio_url.isnot(None)) | (PostModel.video_url.isnot(None))
    ),
}
