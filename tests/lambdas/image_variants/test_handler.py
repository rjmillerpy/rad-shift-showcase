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


def _put_image(s3, key: str, size: tuple[int, int], fmt: str = "JPEG", **options) -> None:
    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, format=fmt, **options)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())


def _event(key: str) -> dict:
    """An S3 ObjectCreated notification, keys URL-encoded as S3 sends them."""
    return {
        "Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key.replace(" ", "+")}}}]
    }


def _image(s3, key: str) -> Image.Image:
    return Image.open(io.BytesIO(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()))


class TestVariants:
    def test_a_large_photo_gets_every_width(self, s3):
        _put_image(s3, "posts/alice_1_0.jpg", (2000, 1500))
        written = handler.process(BUCKET, "posts/alice_1_0.jpg", s3)
        assert written == [f"variants/posts/alice_1_0-{w}.webp" for w in VARIANT_WIDTHS]
        assert [_image(s3, key).size for key in written] == [(480, 360), (1280, 960)]

    def test_variants_are_public_cacheable_webp(self, s3):
        _put_image(s3, "posts/alice_1_0.png", (1000, 1000), fmt="PNG")
        (key,) = handler.process(BUCKET, "posts/alice_1_0.png", s3)
        head = s3.head_object(Bucket=BUCKET, Key=key)
        assert head["ContentType"] == VARIANT_CONTENT_TYPE
        assert head["CacheControl"] == CACHE_CONTROL
        grants = s3.get_object_acl(Bucket=BUCKET, Key=key)["Grants"]
        assert any(g["Grantee"].get("URI", "").endswith("AllUsers") for g in grants)
        assert _image(s3, key).format == "WEBP"

    def test_never_upscaled(self, s3):
        _put_image(s3, "posts/small_1_0.jpg", (300, 200))
        assert handler.process(BUCKET, "posts/small_1_0.jpg", s3) == []

    def test_a_rotated_phone_photo_is_resized_upright(self, s3):
        exif = Image.Exif()
        exif[ExifTags.Base.Orientation] = 6  # rotate 90° clockwise to display
        _put_image(s3, "posts/tall_1_0.jpg", (2000, 1000), exif=exif)
        written = handler.process(BUCKET, "posts/tall_1_0.jpg", s3)
        assert _image(s3, written[0]).size == (480, 960)

    def test_a_greyscale_image_becomes_a_colour_webp(self, s3):
        buf = io.BytesIO()
        Image.new("L", (1000, 500), 128).save(buf, format="PNG")
        s3.put_object(Bucket=BUCKET, Key="posts/grey_1_0.png", Body=buf.getvalue())
        key = handler.process(BUCKET, "posts/grey_1_0.png", s3)[0]
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
        assert handler.process(BUCKET, "variants/posts/a_1_0-1280.webp", s3) == []

    def test_the_prefixes_differ(self):
        assert not VARIANT_PREFIX.startswith(SOURCE_PREFIX)
        assert not SOURCE_PREFIX.startswith(VARIANT_PREFIX)


class TestWhatIsSkipped:
    @pytest.mark.parametrize("key", ["posts/clip_1.mp4", "posts/a_1_doc_0.pdf", "avatars/x.png"])
    def test_non_post_images(self, s3, key):
        assert handler.process(BUCKET, key, s3) == []

    def test_an_unreadable_image_is_logged_and_skipped(self, s3, monkeypatch):
        s3.put_object(Bucket=BUCKET, Key="posts/broken_1_0.jpg", Body=b"not an image")
        monkeypatch.setattr(handler, "_s3", s3)
        assert handler.handler(_event("posts/broken_1_0.jpg"), None) == {"written": []}


class TestHandler:
    def test_handles_every_record_and_decodes_keys(self, s3, monkeypatch):
        _put_image(s3, "posts/with space_1_0.jpg", (1000, 800))
        monkeypatch.setattr(handler, "_s3", s3)
        result = handler.handler(_event("posts/with space_1_0.jpg"), None)
        assert result == {"written": ["variants/posts/with space_1_0-480.webp"]}

    def test_an_event_without_records_does_nothing(self):
        assert handler.handler({}, None) == {"written": []}
