"""Tests for lambdas/image_variants/handler.py, against moto's in-memory S3."""

import io
import os
from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws
from PIL import ExifTags, Image

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")

from lambdas.image_variants import handler  # noqa: E402 - needs the region set first
from lambdas.image_variants.constants import (  # noqa: E402
    CACHE_CONTROL,
    SOURCE_PREFIX,
    VARIANT_CONTENT_TYPE,
    VARIANT_PREFIX,
    VARIANT_WIDTHS,
)

BUCKET = "radshift-test-media"


@pytest.fixture()
def s3() -> Iterator[object]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-2")
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        yield client


@pytest.fixture()
def wired(s3, monkeypatch) -> object:
    """The handler's S3 client pointed at moto."""
    monkeypatch.setattr(handler, "_s3", s3)
    return s3


def _put_image(s3, key: str, size: tuple[int, int], fmt: str = "JPEG", **options) -> None:
    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, format=fmt, **options)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())


def _event(key: str) -> dict:
    """What the workflow passes: the key URL-encoded, as S3's notification has it."""
    return {"bucket": BUCKET, "key": key.replace(" ", "+")}


def _image(s3, key: str) -> Image.Image:
    return Image.open(io.BytesIO(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()))


class TestVariants:
    def test_a_large_photo_gets_every_width(self, s3):
        _put_image(s3, "posts/alice_1_0.jpg", (2000, 1500))
        width, written = handler.process(BUCKET, "posts/alice_1_0.jpg", s3)
        assert width == 2000
        assert written == {w: f"variants/posts/alice_1_0-{w}.webp" for w in VARIANT_WIDTHS}
        assert [_image(s3, key).size for key in written.values()] == [(480, 360), (1280, 960)]

    def test_variants_are_public_cacheable_webp(self, s3):
        _put_image(s3, "posts/alice_1_0.png", (1000, 1000), fmt="PNG")
        (key,) = handler.process(BUCKET, "posts/alice_1_0.png", s3)[1].values()
        head = s3.head_object(Bucket=BUCKET, Key=key)
        assert head["ContentType"] == VARIANT_CONTENT_TYPE
        assert head["CacheControl"] == CACHE_CONTROL
        grants = s3.get_object_acl(Bucket=BUCKET, Key=key)["Grants"]
        assert any(g["Grantee"].get("URI", "").endswith("AllUsers") for g in grants)
        assert _image(s3, key).format == "WEBP"

    def test_never_upscaled(self, s3):
        _put_image(s3, "posts/small_1_0.jpg", (300, 200))
        assert handler.process(BUCKET, "posts/small_1_0.jpg", s3) == (300, {})

    def test_a_rotated_phone_photo_is_resized_upright(self, s3):
        exif = Image.Exif()
        exif[ExifTags.Base.Orientation] = 6  # rotate 90° clockwise to display
        _put_image(s3, "posts/tall_1_0.jpg", (2000, 1000), exif=exif)
        width, written = handler.process(BUCKET, "posts/tall_1_0.jpg", s3)
        assert width == 1000  # the upright width, not the stored one
        assert _image(s3, written[480]).size == (480, 960)

    def test_a_greyscale_image_becomes_a_colour_webp(self, s3):
        buf = io.BytesIO()
        Image.new("L", (1000, 500), 128).save(buf, format="PNG")
        s3.put_object(Bucket=BUCKET, Key="posts/grey_1_0.png", Body=buf.getvalue())
        key = handler.process(BUCKET, "posts/grey_1_0.png", s3)[1][480]
        assert _image(s3, key).mode == "RGB"

    def test_the_original_is_untouched(self, s3):
        _put_image(s3, "posts/keep_1_0.jpg", (1600, 900))
        before = s3.get_object(Bucket=BUCKET, Key="posts/keep_1_0.jpg")["ETag"]
        handler.process(BUCKET, "posts/keep_1_0.jpg", s3)
        assert s3.get_object(Bucket=BUCKET, Key="posts/keep_1_0.jpg")["ETag"] == before


class TestNoLoop:
    """Writing under its own trigger prefix would re-trigger it forever."""

    def test_variant_keys_are_never_under_the_source_prefix(self):
        key = handler.variant_key("posts/a_1_0.jpg", 480)
        assert key.startswith(VARIANT_PREFIX) and not key.startswith(SOURCE_PREFIX)

    def test_a_variant_is_never_processed(self, s3):
        _put_image(s3, "variants/posts/a_1_0-1280.webp", (1280, 720), fmt="WEBP")
        assert handler.process(BUCKET, "variants/posts/a_1_0-1280.webp", s3) == (0, {})

    def test_the_prefixes_differ(self):
        assert not VARIANT_PREFIX.startswith(SOURCE_PREFIX)
        assert not SOURCE_PREFIX.startswith(VARIANT_PREFIX)


class TestWhatIsSkipped:
    @pytest.mark.parametrize("key", ["posts/clip_1.mp4", "posts/a_1_doc_0.pdf", "avatars/x.png"])
    def test_non_post_images(self, s3, key):
        assert handler.process(BUCKET, key, s3) == (0, {})

    def test_an_unreadable_image_is_skipped_not_raised(self, wired):
        """Retrying can't fix a broken file, so it must not fail the workflow."""
        wired.put_object(Bucket=BUCKET, Key="posts/broken_1_0.jpg", Body=b"not an image")
        assert handler.handler(_event("posts/broken_1_0.jpg"), None) == {
            "skipped": "UnidentifiedImageError"
        }

    def test_a_non_image_is_skipped(self, wired):
        assert handler.handler(_event("posts/clip_1.mp4"), None) == {"skipped": "no variants"}


class TestHandler:
    def test_the_result_is_what_the_api_reads(self, wired):
        _put_image(wired, "posts/with space_1_0.jpg", (1000, 800))
        assert handler.handler(_event("posts/with space_1_0.jpg"), None) == {
            "bucket": BUCKET,
            "source_key": "posts/with space_1_0.jpg",
            "width": 1000,
            "variants": {"480": "variants/posts/with space_1_0-480.webp"},
        }

    def test_an_image_too_small_for_any_variant_is_skipped(self, wired):
        _put_image(wired, "posts/tiny_1_0.jpg", (200, 200))
        assert handler.handler(_event("posts/tiny_1_0.jpg"), None) == {"skipped": "no variants"}

    def test_a_missing_object_raises_for_the_workflow_to_retry(self, wired):
        with pytest.raises(wired.exceptions.NoSuchKey):
            handler.handler(_event("posts/gone_1_0.jpg"), None)
