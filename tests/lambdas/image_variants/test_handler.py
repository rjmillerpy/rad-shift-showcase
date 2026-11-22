"""Tests for lambdas/image_variants/handler.py, against moto's in-memory S3 and SQS."""

import io
import json
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
    RESULTS_QUEUE_URL_ENV,
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
def results(s3, monkeypatch) -> object:
    """The results queue, with the handler's clients pointed at moto."""
    sqs = boto3.client("sqs", region_name="us-east-2")
    url = sqs.create_queue(QueueName="radshift-test-results")["QueueUrl"]
    monkeypatch.setenv(RESULTS_QUEUE_URL_ENV, url)
    monkeypatch.setattr(handler, "_s3", s3)
    monkeypatch.setattr(handler, "_sqs", sqs)

    class Results:
        def read(self) -> list[dict]:
            messages = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", [])
            return [json.loads(m["Body"]) for m in messages]

    return Results()


def _put_image(s3, key: str, size: tuple[int, int], fmt: str = "JPEG", **options) -> None:
    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, format=fmt, **options)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())


def _notification(*keys: str) -> str:
    """An S3 ObjectCreated notification body, keys URL-encoded as S3 sends them."""
    records = [
        {"s3": {"bucket": {"name": BUCKET}, "object": {"key": key.replace(" ", "+")}}}
        for key in keys
    ]
    return json.dumps({"Records": records})


def _batch(*bodies: str) -> dict:
    """An SQS event as Lambda delivers it, one message per body."""
    return {"Records": [{"messageId": f"m{i}", "body": body} for i, body in enumerate(bodies)]}


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

    def test_an_unreadable_image_is_done_not_retried(self, s3, results):
        """Retrying can't fix a broken file, so it must not end in the dead-letter queue."""
        s3.put_object(Bucket=BUCKET, Key="posts/broken_1_0.jpg", Body=b"not an image")
        response = handler.handler(_batch(_notification("posts/broken_1_0.jpg")), None)
        assert response == {"batchItemFailures": []}
        assert results.read() == []

    def test_s3s_test_event_is_done(self, results):
        test_event = json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent"})
        assert handler.handler(_batch(test_event), None) == {"batchItemFailures": []}


class TestHandler:
    def test_results_are_reported_for_the_api(self, s3, results):
        _put_image(s3, "posts/with space_1_0.jpg", (1000, 800))
        response = handler.handler(_batch(_notification("posts/with space_1_0.jpg")), None)
        assert response == {"batchItemFailures": []}
        assert results.read() == [
            {
                "bucket": BUCKET,
                "source_key": "posts/with space_1_0.jpg",
                "width": 1000,
                "variants": {"480": "variants/posts/with space_1_0-480.webp"},
            }
        ]

    def test_an_image_too_small_for_any_variant_reports_nothing(self, s3, results):
        _put_image(s3, "posts/tiny_1_0.jpg", (200, 200))
        handler.handler(_batch(_notification("posts/tiny_1_0.jpg")), None)
        assert results.read() == []

    def test_every_object_in_a_notification(self, s3, results):
        _put_image(s3, "posts/a_1_0.jpg", (1000, 800))
        _put_image(s3, "posts/b_1_0.jpg", (1000, 800))
        handler.handler(_batch(_notification("posts/a_1_0.jpg", "posts/b_1_0.jpg")), None)
        assert {r["source_key"] for r in results.read()} == {"posts/a_1_0.jpg", "posts/b_1_0.jpg"}

    def test_only_the_failing_message_is_retried(self, s3, results):
        """A missing object (S3 error) fails its own message, not the batch."""
        _put_image(s3, "posts/ok_1_0.jpg", (1000, 800))
        batch = _batch(_notification("posts/gone_1_0.jpg"), _notification("posts/ok_1_0.jpg"))
        assert handler.handler(batch, None) == {"batchItemFailures": [{"itemIdentifier": "m0"}]}
        assert [r["source_key"] for r in results.read()] == ["posts/ok_1_0.jpg"]

    def test_a_malformed_body_is_retried_then_parked(self, results):
        assert handler.handler(_batch("not json"), None) == {
            "batchItemFailures": [{"itemIdentifier": "m0"}]
        }

    def test_a_result_that_cant_be_sent_is_retried(self, s3, results, monkeypatch):
        """The variants exist but the API wouldn't hear of them: retry the message."""
        _put_image(s3, "posts/a_1_0.jpg", (1000, 800))
        monkeypatch.setenv(
            RESULTS_QUEUE_URL_ENV, "https://sqs.us-east-2.amazonaws.com/123456789012/missing"
        )
        response = handler.handler(_batch(_notification("posts/a_1_0.jpg")), None)
        assert response == {"batchItemFailures": [{"itemIdentifier": "m0"}]}

    def test_an_event_without_records_does_nothing(self):
        assert handler.handler({}, None) == {"batchItemFailures": []}
