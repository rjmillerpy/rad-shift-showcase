"""Strip metadata from uploaded images before they are stored and served.

Phone photos carry EXIF metadata: GPS coordinates, the device, the time
taken. Uploads are public, so every raster image is decoded and re-encoded
with none of it (EXIF, XMP, comments, text chunks), keeping only the colour
profile. The EXIF orientation is applied to the pixels first, so a portrait
photo still displays upright once its orientation tag is gone.

HEIC/HEIF (iPhones' default) is converted to JPEG: most browsers can't
display HEIC anyway. SVG is text, not pixels, and passes through unchanged.
"""

import io
import logging
import warnings
from dataclasses import dataclass
from typing import BinaryIO

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError
from pillow_heif import register_heif_opener

logger = logging.getLogger(__name__)

register_heif_opener()

JPEG_QUALITY = 90
# Pillow's format name for each extension it re-encodes. HEIC/HEIF become JPEG.
_SAVE_FORMATS = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "heic": "JPEG",
    "heif": "JPEG",
    "png": "PNG",
    "gif": "GIF",
    "webp": "WEBP",
    "avif": "AVIF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "tif": "TIFF",
    "ico": "ICO",
}
_CONVERTED_EXTENSIONS = {"heic": "jpg", "heif": "jpg"}
# Formats that can hold several frames; saving keeps every frame.
_ANIMATED_FORMATS = {"GIF", "WEBP", "AVIF"}
# What an image may keep from its source: how it displays, nothing about
# who took it or where. Some encoders (GIF's comment) copy anything else.
_KEPT_INFO = frozenset(
    {"icc_profile", "transparency", "background", "duration", "loop", "disposal", "dpi"}
)
PASSTHROUGH_EXTENSIONS = frozenset({"svg"})


class InvalidImageError(ValueError):
    """The upload claims an image extension but isn't a readable image."""


@dataclass(frozen=True)
class CleanImage:
    data: BinaryIO
    # Changes only when the format does (HEIC -> jpg).
    extension: str


def strip_metadata(fileobj: BinaryIO, extension: str) -> CleanImage:
    """The image re-encoded without metadata (or unchanged, for SVG)."""
    if extension in PASSTHROUGH_EXTENSIONS:
        return CleanImage(fileobj, extension)
    save_format = _SAVE_FORMATS.get(extension)
    if save_format is None:
        raise InvalidImageError(f"not a raster image extension: {extension!r}")
    image = _open(fileobj)
    out = io.BytesIO()
    _save(image, out, save_format)
    out.seek(0)
    return CleanImage(out, _CONVERTED_EXTENSIONS.get(extension, extension))


def _open(fileobj: BinaryIO) -> Image.Image:
    try:
        with warnings.catch_warnings():
            # A decompression bomb (an image that expands to enormous pixel
            # counts) is refused outright, not merely warned about.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(fileobj)
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombWarning) as err:
        raise InvalidImageError(f"unreadable image: {type(err).__name__}") from err
    except Image.DecompressionBombError as err:
        raise InvalidImageError("image too large to decode") from err
    return image


def _kept_info(image: Image.Image) -> dict:
    return {key: value for key, value in image.info.items() if key in _KEPT_INFO}


def _save(image: Image.Image, out: io.BytesIO, save_format: str) -> None:
    icc_profile = image.info.get("icc_profile")
    if getattr(image, "is_animated", False) and save_format in _ANIMATED_FORMATS:
        _save_animation(image, out, save_format)
        return
    upright = ImageOps.exif_transpose(image)
    upright.info = _kept_info(upright)
    if save_format == "JPEG" and upright.mode not in ("RGB", "L"):
        upright = upright.convert("RGB")
    options: dict[str, object] = {"icc_profile": icc_profile} if icc_profile else {}
    if save_format == "JPEG":
        options["quality"] = JPEG_QUALITY
    upright.save(out, format=save_format, **options)


def _save_animation(image: Image.Image, out: io.BytesIO, save_format: str) -> None:
    # Copied out frame by frame: saving the source directly re-reads each
    # frame's original info (a GIF's comment) as it goes. Orientation tags are
    # a photo thing, not an animation one, so nothing is transposed.
    frames = []
    for frame in ImageSequence.Iterator(image):
        copy = frame.copy()
        copy.info = _kept_info(frame)
        frames.append(copy)
    first, *rest = frames
    first.save(
        out,
        format=save_format,
        save_all=True,
        append_images=rest,
        duration=[frame.info.get("duration", 0) for frame in frames],
        loop=image.info.get("loop", 0),
    )
