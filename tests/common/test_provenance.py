"""Tests for app/common/provenance.py on real image files carrying AI markers."""

import io

import pytest
from PIL import Image

from app.common.provenance import declares_ai_generated
from tests.helpers import jpeg_with_c2pa_segment, jpeg_with_xmp, png_with_xmp


@pytest.mark.parametrize(
    "image",
    [
        jpeg_with_xmp("trainedAlgorithmicMedia"),
        jpeg_with_xmp("compositeWithTrainedAlgorithmicMedia"),
        png_with_xmp("trainedAlgorithmicMedia"),
        jpeg_with_c2pa_segment(),
    ],
    ids=["jpeg-xmp", "jpeg-xmp-composite", "png-xmp", "jpeg-c2pa"],
)
def test_an_image_marked_as_ai_is_found(image):
    assert declares_ai_generated(image)


@pytest.mark.parametrize(
    "image",
    [
        jpeg_with_xmp("digitalCapture"),
        jpeg_with_xmp("algorithmicMedia"),
        png_with_xmp("digitalCapture"),
    ],
    ids=["camera-photo", "procedural-not-ai", "png-photo"],
)
def test_other_source_types_are_not_ai(image):
    assert not declares_ai_generated(image)


def test_an_image_with_no_metadata_proves_nothing_either_way():
    plain = io.BytesIO()
    Image.new("RGB", (8, 8)).save(plain, format="JPEG")
    assert not declares_ai_generated(plain)


def test_a_marker_split_across_two_reads_is_found():
    term = b"trainedAlgorithmicMedia"
    boundary = 1024 * 1024  # the scanner's read size
    data = b"\x00" * (boundary - 10) + term + b"\x00" * 100
    assert declares_ai_generated(io.BytesIO(data))


def test_the_file_is_left_at_its_start_for_whatever_reads_it_next():
    image = jpeg_with_xmp("trainedAlgorithmicMedia")
    image.seek(50)
    declares_ai_generated(image)
    assert image.tell() == 0
