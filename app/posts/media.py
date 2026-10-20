"""Extract metadata (duration, format, bitrate) from uploaded media files."""

import json
import logging
import os
import shutil
import subprocess  # nosec B404 - only runs ffprobe with an argument list
import tempfile
from typing import IO

logger = logging.getLogger(__name__)

FFPROBE_TIMEOUT_SECONDS = 10


def extract_audio_metadata(fileobj: IO[bytes], extension: str) -> dict | None:
    """Extract duration, bitrate, sample_rate from audio using mutagen."""
    try:
        import mutagen
    except ImportError:
        logger.warning("mutagen not installed — skipping audio metadata extraction")
        return None

    fileobj.seek(0)
    try:
        audio = mutagen.File(fileobj)
    except Exception as exc:  # noqa: BLE001
        # The file is an untrusted upload and mutagen's parsers raise more
        # than MutagenError on corrupt input (struct.error, IndexError, ...).
        # Metadata is optional, so any parse failure means "no metadata",
        # never a failed upload. Logged so a pattern of failures is visible.
        logger.warning("mutagen failed to read audio file: %s", exc)
        return None

    if audio is None:
        return None

    info = audio.info if hasattr(audio, "info") else None
    if info is None:
        return None

    return {
        "duration_seconds": round(info.length, 2) if hasattr(info, "length") else None,
        "bitrate": info.bitrate if hasattr(info, "bitrate") else None,
        "sample_rate": info.sample_rate if hasattr(info, "sample_rate") else None,
        "format": extension,
        "type": "audio",
    }


def _run_ffprobe(ffprobe: str, path: str) -> dict | None:
    """Run ffprobe on `path` and return its parsed JSON report, or None if
    ffprobe rejected the file."""
    result = subprocess.run(  # nosec B603 - fixed argv, no shell; the only input is our temp file path
        [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True,
        text=True,
        timeout=FFPROBE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def _video_metadata_from_probe(probe: dict, extension: str) -> dict:
    """Pick duration, bitrate and dimensions out of an ffprobe report."""
    fmt = probe.get("format", {})
    video_stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    duration_str = fmt.get("duration")
    bitrate_str = fmt.get("bit_rate")
    width = int(video_stream["width"]) if video_stream and "width" in video_stream else None
    height = int(video_stream["height"]) if video_stream and "height" in video_stream else None
    return {
        "duration_seconds": round(float(duration_str), 2) if duration_str else None,
        "bitrate": int(bitrate_str) if bitrate_str else None,
        "dimensions": {"width": width, "height": height} if width and height else None,
        "format": extension,
        "type": "video",
    }


def extract_video_metadata_ffprobe(fileobj: IO[bytes], extension: str) -> dict | None:
    """Extract video metadata using ffprobe (if available on system)."""
    # Absolute path, so a writable directory earlier on PATH can't substitute
    # its own "ffprobe".
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        logger.info("ffprobe not installed — skipping video metadata extraction")
        return None

    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as tmp:
        tmp_path = tmp.name
        fileobj.seek(0)
        tmp.write(fileobj.read())

    try:
        probe = _run_ffprobe(ffprobe, tmp_path)
        return _video_metadata_from_probe(probe, extension) if probe is not None else None
    except FileNotFoundError:
        logger.info("ffprobe not installed — skipping video metadata extraction")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out after %ds", FFPROBE_TIMEOUT_SECONDS)
        return None
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("ffprobe output parse error: %s", exc)
        return None
    finally:
        os.unlink(tmp_path)
        fileobj.seek(0)


def extract_media_metadata(fileobj: IO[bytes], extension: str) -> dict | None:
    """Dispatch to the appropriate extractor based on file extension."""
    from app.posts.constants import ALLOWED_AUDIO_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS

    if extension in ALLOWED_AUDIO_EXTENSIONS:
        return extract_audio_metadata(fileobj, extension)
    if extension in ALLOWED_VIDEO_EXTENSIONS:
        return extract_video_metadata_ffprobe(fileobj, extension)
    return None
