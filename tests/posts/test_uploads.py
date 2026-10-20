"""Unit tests for app/posts/uploads.py — filename sanitisation, size checks, S3 keys."""

import io
from types import SimpleNamespace

import pytest

from app.posts import uploads
from app.posts.constants import (
    ALLOWED_ARCHIVE_EXTENSIONS,
    ALLOWED_DOCUMENT_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
)


class TestSanitizeS3KeyPart:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("normal_user.1", "normal_user.1"),
            ("my-user", "my-user"),
            ("../../etc/passwd", ".._.._etc_passwd"),
            ("user/hack", "user_hack"),
            ("emoji😀name", "emoji_name"),
            ("path with spaces", "path_with_spaces"),
        ],
        ids=["safe", "hyphen", "traversal", "slash", "unicode", "spaces"],
    )
    def test_output_shape(self, raw, expected):
        assert uploads._sanitize_s3_key_part(raw) == expected

    def test_slash_never_survives(self):
        assert "/" not in uploads._sanitize_s3_key_part("///")


def _fake_upload(filename: str, size: int) -> SimpleNamespace:
    """Stand-in for FastAPI's UploadFile — only exposes .filename and .file."""
    return SimpleNamespace(filename=filename, file=io.BytesIO(b"x" * size))


class TestValidateUpload:
    def test_accepts_valid(self):
        assert uploads._validate_upload(_fake_upload("photo.jpg", 100), "jpg") is True

    def test_rejects_disallowed_extension(self):
        assert uploads._validate_upload(_fake_upload("evil.exe", 100), "exe") is False

    def test_rejects_oversize(self):
        big = _fake_upload("big.jpg", MAX_FILE_SIZE_BYTES + 1)
        assert uploads._validate_upload(big, "jpg") is False

    def test_seek_pos_is_reset_after_check(self):
        f = _fake_upload("photo.jpg", 100)
        uploads._validate_upload(f, "jpg")
        assert f.file.tell() == 0


class TestBuildS3Key:
    def _counters(self):
        return {"img": 0, "doc": 0}

    def test_image_key_uses_img_counter(self):
        counters = self._counters()
        k1 = uploads._build_s3_key("jpg", "alice", 1000, counters)
        k2 = uploads._build_s3_key("png", "alice", 1000, counters)
        assert k1 == "posts/alice_1000_0.jpg"
        assert k2 == "posts/alice_1000_1.png"

    def test_document_key_uses_doc_counter(self):
        counters = self._counters()
        for ext in list(ALLOWED_DOCUMENT_EXTENSIONS)[:1]:
            key = uploads._build_s3_key(ext, "alice", 1000, counters)
            assert "doc_" in key
            assert key.endswith(f".{ext}")

    def test_archive_key_uses_doc_counter(self):
        counters = self._counters()
        for ext in list(ALLOWED_ARCHIVE_EXTENSIONS)[:1]:
            key = uploads._build_s3_key(ext, "alice", 1000, counters)
            assert "doc_" in key

    def test_video_key_no_counter(self):
        counters = self._counters()
        key = uploads._build_s3_key("mp4", "alice", 1000, counters)
        assert key == "posts/alice_1000.mp4"


class TestGetMultimediaUrls:
    def _files(self, mapping: dict[str, SimpleNamespace]) -> dict:
        return mapping

    def test_empty_input(self):
        result = uploads.get_multimedia_urls({}, "alice", 1000)
        assert result == {
            "image_url": None,
            "image_urls": None,
            "video_url": None,
            "audio_url": None,
            "document_urls": None,
            "media_metadata": None,
        }

    def test_single_image_populates_both_fields(self):
        result = uploads.get_multimedia_urls(
            {"image_0": _fake_upload("photo.jpg", 100)},
            "alice",
            1000,
        )
        assert result["image_url"] is not None
        assert result["image_urls"] == [result["image_url"]]

    def test_multiple_images_return_list(self):
        files = {f"image_{i}": _fake_upload(f"p{i}.jpg", 100) for i in range(3)}
        result = uploads.get_multimedia_urls(files, "alice", 1000)
        assert len(result["image_urls"]) == 3

    def test_video_and_audio_slots(self):
        files = {
            "video": _fake_upload("v.mp4", 100),
            "audio": _fake_upload("a.mp3", 100),
        }
        result = uploads.get_multimedia_urls(files, "alice", 1000)
        assert result["video_url"] is not None
        assert result["audio_url"] is not None

    def test_disallowed_file_dropped(self):
        result = uploads.get_multimedia_urls(
            {"image_0": _fake_upload("evil.exe", 100)},
            "alice",
            1000,
        )
        assert result["image_urls"] is None
