"""Tests for app/posts/media.py — audio/video metadata extraction."""

import io
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.posts.media import (
    extract_audio_metadata,
    extract_media_metadata,
    extract_video_metadata_ffprobe,
)


class TestExtractAudioMetadata:
    """Tests for extract_audio_metadata."""

    def test_returns_metadata_from_mutagen(self):
        """Valid mutagen File object produces the expected metadata dict."""
        mock_info = SimpleNamespace(length=123.456, bitrate=320000, sample_rate=44100)
        mock_audio = MagicMock()
        mock_audio.info = mock_info

        mock_mutagen = MagicMock()
        mock_mutagen.File.return_value = mock_audio

        fileobj = io.BytesIO(b"fake audio data")

        with patch.dict("sys.modules", {"mutagen": mock_mutagen}):
            result = extract_audio_metadata(fileobj, "mp3")

        assert result is not None
        assert result["duration_seconds"] == 123.46
        assert result["bitrate"] == 320000
        assert result["sample_rate"] == 44100
        assert result["format"] == "mp3"
        assert result["type"] == "audio"

    def test_returns_none_when_mutagen_not_installed(self):
        """Gracefully returns None when mutagen import fails."""
        fileobj = io.BytesIO(b"fake audio data")

        with patch.dict("sys.modules", {"mutagen": None}):
            result = extract_audio_metadata(fileobj, "mp3")

        assert result is None

    def test_returns_none_when_mutagen_returns_none(self):
        """Returns None when mutagen.File cannot parse the file."""
        mock_mutagen = MagicMock()
        mock_mutagen.File.return_value = None
        fileobj = io.BytesIO(b"fake audio data")

        with patch.dict("sys.modules", {"mutagen": mock_mutagen}):
            result = extract_audio_metadata(fileobj, "wav")

        assert result is None

    def test_returns_none_when_mutagen_raises(self):
        """Returns None when mutagen.File raises an exception."""
        mock_mutagen = MagicMock()
        mock_mutagen.File.side_effect = Exception("corrupt file")
        fileobj = io.BytesIO(b"corrupt data")

        with patch.dict("sys.modules", {"mutagen": mock_mutagen}):
            result = extract_audio_metadata(fileobj, "mp3")

        assert result is None

    def test_handles_missing_info_attributes(self):
        """Returns None values for missing info attributes (e.g. no bitrate)."""
        mock_info = SimpleNamespace(length=60.0)
        mock_audio = MagicMock()
        mock_audio.info = mock_info

        mock_mutagen = MagicMock()
        mock_mutagen.File.return_value = mock_audio
        fileobj = io.BytesIO(b"fake audio")

        with patch.dict("sys.modules", {"mutagen": mock_mutagen}):
            result = extract_audio_metadata(fileobj, "ogg")

        assert result is not None
        assert result["duration_seconds"] == 60.0
        assert result["bitrate"] is None
        assert result["sample_rate"] is None


class TestExtractVideoMetadataFfprobe:
    """Tests for extract_video_metadata_ffprobe."""

    @pytest.fixture(autouse=True)
    def _ffprobe_on_path(self):
        """Pretend ffprobe is installed; subprocess.run is mocked per test."""
        with patch("app.posts.media.shutil.which", return_value="/usr/bin/ffprobe"):
            yield

    def test_returns_none_when_ffprobe_not_installed(self):
        """Returns None gracefully, without running anything, when ffprobe is missing."""
        fileobj = io.BytesIO(b"fake video data")

        with (
            patch("app.posts.media.shutil.which", return_value=None),
            patch("app.posts.media.subprocess.run") as run,
        ):
            result = extract_video_metadata_ffprobe(fileobj, "mp4")
        run.assert_not_called()

        assert result is None

    def test_returns_none_on_nonzero_exit(self):
        """Returns None when ffprobe exits with non-zero status."""
        fileobj = io.BytesIO(b"fake video data")
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("app.posts.media.subprocess.run", return_value=mock_result):
            result = extract_video_metadata_ffprobe(fileobj, "mp4")

        assert result is None

    def test_returns_none_on_timeout(self):
        """Returns None when ffprobe exceeds timeout."""
        fileobj = io.BytesIO(b"fake video data")

        with patch(
            "app.posts.media.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=10),
        ):
            result = extract_video_metadata_ffprobe(fileobj, "mp4")

        assert result is None

    def test_extracts_metadata_successfully(self):
        """Parses valid ffprobe JSON output into metadata dict."""
        ffprobe_output = json.dumps(
            {
                "format": {
                    "duration": "120.500",
                    "bit_rate": "2500000",
                },
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                    },
                    {
                        "codec_type": "audio",
                        "sample_rate": "48000",
                    },
                ],
            }
        )

        fileobj = io.BytesIO(b"fake video data")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ffprobe_output

        with patch("app.posts.media.subprocess.run", return_value=mock_result):
            result = extract_video_metadata_ffprobe(fileobj, "mp4")

        assert result is not None
        assert result["duration_seconds"] == 120.5
        assert result["bitrate"] == 2500000
        assert result["dimensions"] == {"width": 1920, "height": 1080}
        assert result["format"] == "mp4"
        assert result["type"] == "video"

    def test_returns_none_on_invalid_json(self):
        """Returns None when ffprobe outputs invalid JSON."""
        fileobj = io.BytesIO(b"fake video data")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"

        with patch("app.posts.media.subprocess.run", return_value=mock_result):
            result = extract_video_metadata_ffprobe(fileobj, "mp4")

        assert result is None

    def test_handles_missing_video_stream(self):
        """Returns None dimensions when no video stream exists."""
        ffprobe_output = json.dumps(
            {
                "format": {"duration": "30.0", "bit_rate": "128000"},
                "streams": [{"codec_type": "audio"}],
            }
        )
        fileobj = io.BytesIO(b"fake")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ffprobe_output

        with patch("app.posts.media.subprocess.run", return_value=mock_result):
            result = extract_video_metadata_ffprobe(fileobj, "webm")

        assert result is not None
        assert result["dimensions"] is None
        assert result["duration_seconds"] == 30.0


class TestExtractMediaMetadata:
    """Tests for the dispatch function extract_media_metadata."""

    @pytest.mark.parametrize(
        "extension,expected_dispatcher",
        [
            ("mp3", "extract_audio_metadata"),
            ("wav", "extract_audio_metadata"),
            ("ogg", "extract_audio_metadata"),
            ("aac", "extract_audio_metadata"),
            ("flac", "extract_audio_metadata"),
            ("mp4", "extract_video_metadata_ffprobe"),
            ("mov", "extract_video_metadata_ffprobe"),
            ("webm", "extract_video_metadata_ffprobe"),
            ("avi", "extract_video_metadata_ffprobe"),
            ("mkv", "extract_video_metadata_ffprobe"),
        ],
        ids=[
            "mp3-dispatches-to-audio",
            "wav-dispatches-to-audio",
            "ogg-dispatches-to-audio",
            "aac-dispatches-to-audio",
            "flac-dispatches-to-audio",
            "mp4-dispatches-to-video",
            "mov-dispatches-to-video",
            "webm-dispatches-to-video",
            "avi-dispatches-to-video",
            "mkv-dispatches-to-video",
        ],
    )
    def test_dispatches_to_correct_extractor(self, extension, expected_dispatcher):
        """Extension-based dispatch calls the right extractor function."""
        fileobj = io.BytesIO(b"data")
        sentinel = {"type": "test", "format": extension}

        with patch(f"app.posts.media.{expected_dispatcher}", return_value=sentinel) as mock_fn:
            result = extract_media_metadata(fileobj, extension)

        mock_fn.assert_called_once_with(fileobj, extension)
        assert result == sentinel

    @pytest.mark.parametrize(
        "extension",
        ["jpg", "png", "gif", "pdf", "txt", "zip"],
        ids=[
            "jpg-returns-none",
            "png-returns-none",
            "gif-returns-none",
            "pdf-returns-none",
            "txt-returns-none",
            "zip-returns-none",
        ],
    )
    def test_returns_none_for_non_media_extensions(self, extension):
        """Non-audio/video extensions return None without calling any extractor."""
        fileobj = io.BytesIO(b"data")

        with (
            patch("app.posts.media.extract_audio_metadata") as mock_audio,
            patch("app.posts.media.extract_video_metadata_ffprobe") as mock_video,
        ):
            result = extract_media_metadata(fileobj, extension)

        mock_audio.assert_not_called()
        mock_video.assert_not_called()
        assert result is None
