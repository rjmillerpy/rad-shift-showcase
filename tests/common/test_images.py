"""Tests for app/common/images.py: real images carrying real metadata."""

import io

import pillow_heif
import pytest
from PIL import ExifTags, Image, PngImagePlugin

from app.common.images import (
    JPEG_QUALITY,
    InvalidImageError,
    strip_metadata,
)

# Chicago, written as an EXIF GPS block the way a phone would.
GPS = {
    ExifTags.GPS.GPSLatitudeRef: "N",
    ExifTags.GPS.GPSLatitude: (41.0, 52.0, 55.0),
    ExifTags.GPS.GPSLongitudeRef: "W",
    ExifTags.GPS.GPSLongitude: (87.0, 37.0, 40.0),
}
XMP = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:Description>secret-place</rdf:Description></x:xmpmeta>'


def _exif(orientation: int = 1) -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "PhoneCo"
    exif[ExifTags.Base.Orientation] = orientation
    exif.get_ifd(ExifTags.IFD.GPSInfo).update(GPS)
    return exif


def _encode(image: Image.Image, fmt: str, **options) -> io.BytesIO:
    buf = io.BytesIO()
    image.save(buf, format=fmt, **options)
    buf.seek(0)
    return buf


def _reopen(clean) -> Image.Image:
    image = Image.open(clean.data)
    image.load()
    return image


def _no_metadata(image: Image.Image) -> None:
    assert not image.getexif(), dict(image.getexif())
    for key in ("exif", "xmp", "XML:com.adobe.xmp", "comment", "Description"):
        assert key not in image.info, key


class TestStripping:
    def test_jpeg_loses_gps_and_camera_details(self):
        source = _encode(Image.new("RGB", (40, 30), "red"), "JPEG", exif=_exif())
        clean = strip_metadata(source, "jpg")
        assert clean.extension == "jpg"
        image = _reopen(clean)
        assert image.format == "JPEG"
        _no_metadata(image)

    def test_png_loses_exif_and_text_chunks(self):
        text = PngImagePlugin.PngInfo()
        text.add_text("Description", "taken at home")
        source = _encode(Image.new("RGBA", (10, 10)), "PNG", exif=_exif(), pnginfo=text)
        _no_metadata(_reopen(strip_metadata(source, "png")))

    def test_webp_loses_exif_and_xmp(self):
        source = _encode(Image.new("RGB", (10, 10)), "WEBP", exif=_exif(), xmp=XMP)
        _no_metadata(_reopen(strip_metadata(source, "webp")))

    def test_gif_loses_its_comment_and_keeps_every_frame(self):
        # Distinct frames: Pillow merges identical consecutive ones when saving.
        frames = [Image.new("RGB", (8, 8), color) for color in ("red", "green", "blue")]
        source = _encode(
            frames[0], "GIF", save_all=True, append_images=frames[1:], comment=b"secret-place"
        )
        image = _reopen(strip_metadata(source, "gif"))
        _no_metadata(image)
        assert image.n_frames == 3

    def test_an_animation_keeps_its_timing_and_loop(self):
        frames = [Image.new("RGB", (8, 8), color) for color in ("red", "green")]
        source = _encode(
            frames[0], "GIF", save_all=True, append_images=frames[1:], duration=[120, 80], loop=2
        )
        image = _reopen(strip_metadata(source, "gif"))
        durations = []
        for index in range(image.n_frames):
            image.seek(index)
            durations.append(image.info["duration"])
        assert durations == [120, 80] and image.info["loop"] == 2

    def test_heic_becomes_a_jpeg_without_metadata(self):
        heif = pillow_heif.from_pillow(Image.new("RGB", (16, 16), "blue"))
        source = io.BytesIO()
        heif.save(source, exif=_exif().tobytes())
        source.seek(0)
        clean = strip_metadata(source, "heic")
        assert clean.extension == "jpg"
        image = _reopen(clean)
        assert image.format == "JPEG"
        _no_metadata(image)

    def test_the_colour_profile_is_kept(self):
        profile = b"\x00" * 128  # opaque bytes are enough: Pillow copies, not parses
        source = _encode(Image.new("RGB", (4, 4)), "PNG", icc_profile=profile)
        assert _reopen(strip_metadata(source, "png")).info.get("icc_profile") == profile


class TestOrientation:
    def test_a_rotated_phone_photo_is_turned_upright(self):
        """Orientation 6 means "rotate 90° clockwise to display": a 40x20 sensor
        image is a 20x40 portrait photo, and must stay one without the tag."""
        source = _encode(Image.new("RGB", (40, 20)), "JPEG", exif=_exif(orientation=6))
        assert _reopen(strip_metadata(source, "jpeg")).size == (20, 40)

    def test_a_cmyk_jpeg_stays_a_readable_jpeg(self):
        source = _encode(Image.new("CMYK", (4, 4)), "JPEG")
        assert _reopen(strip_metadata(source, "jpg")).format == "JPEG"


class TestPassThrough:
    def test_svg_is_unchanged(self):
        source = io.BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        clean = strip_metadata(source, "svg")
        assert clean.data is source and clean.extension == "svg"


class TestRejected:
    def test_a_file_that_is_not_an_image(self):
        with pytest.raises(InvalidImageError):
            strip_metadata(io.BytesIO(b"definitely not a jpeg"), "jpg")

    def test_an_extension_that_is_not_a_raster_format(self):
        with pytest.raises(InvalidImageError):
            strip_metadata(io.BytesIO(b"%PDF-1.7"), "pdf")

    def test_a_decompression_bomb(self, monkeypatch):
        # A tiny limit stands in for a real bomb (gigapixel dimensions).
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
        source = _encode(Image.new("RGB", (5, 5)), "PNG")
        with pytest.raises(InvalidImageError):
            strip_metadata(source, "png")

    def test_a_truncated_image(self):
        whole = _encode(Image.new("RGB", (64, 64), "green"), "PNG").getvalue()
        with pytest.raises(InvalidImageError):
            strip_metadata(io.BytesIO(whole[: len(whole) // 2]), "png")


def test_jpeg_quality_is_high():
    assert 85 <= JPEG_QUALITY <= 95
