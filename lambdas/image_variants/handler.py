"""Lambda entry point: make web-sized variants of each new post image.

S3 queues a notification for every object created under posts/ with an
image extension, and Lambda hands this function batches from that queue
(infra/media-pipeline/queue.tf). For each image it writes a WebP per width
in VARIANT_WIDTHS, under variants/, keyed by the source: posts/a_1_0.jpg
becomes variants/posts/a_1_0-480.webp and -1280.webp. The original is never
changed, so a failure here costs a smaller image, never the post's. Then it
sends the variant keys to the results queue, which the API polls to record
them on the post (app/media/).

A message that fails is reported back by id (ReportBatchItemFailures), so
only it is retried; after three tries SQS parks it in the dead-letter queue
and an alarm emails. A broken image is not a failure: retrying can't fix it.

Runs on AWS's python3.12 runtime, which provides boto3; the deployment zip
carries Pillow and this package at the same path as in the repository, so
the handler is lambdas.image_variants.handler.handler in both
(scripts/build_lambda.sh).
"""

from __future__ import annotations

import io
import json
import logging
import os
import posixpath
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config
from PIL import Image, ImageOps

from lambdas.image_variants.constants import (
    AWS_CONNECT_TIMEOUT_SECONDS,
    AWS_MAX_ATTEMPTS,
    AWS_READ_TIMEOUT_SECONDS,
    CACHE_CONTROL,
    IMAGE_EXTENSIONS,
    MAX_IMAGE_PIXELS,
    PUBLIC_ACL,
    RESULT_BUCKET,
    RESULT_SOURCE_KEY,
    RESULT_VARIANTS,
    RESULT_WIDTH,
    RESULTS_QUEUE_URL_ENV,
    S3_TEST_EVENT,
    SOURCE_PREFIX,
    VARIANT_CONTENT_TYPE,
    VARIANT_PREFIX,
    VARIANT_WIDTHS,
    WEBP_QUALITY,
)

# boto3 ships no type information for its clients.
S3Client = Any
SQSClient = Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# Created once per container and reused across invocations.
_AWS_CONFIG = Config(
    connect_timeout=AWS_CONNECT_TIMEOUT_SECONDS,
    read_timeout=AWS_READ_TIMEOUT_SECONDS,
    retries={"max_attempts": AWS_MAX_ATTEMPTS, "mode": "standard"},
)
_s3: S3Client = boto3.client("s3", config=_AWS_CONFIG)
_sqs: SQSClient = boto3.client("sqs", config=_AWS_CONFIG)


def variant_key(source_key: str, width: int) -> str:
    """variants/<source key without extension>-<width>.webp"""
    stem, _ = posixpath.splitext(source_key)
    return f"{VARIANT_PREFIX}{stem}-{width}.webp"


def is_source(key: str) -> bool:
    """Whether a key is an image this function should resize."""
    extension = posixpath.splitext(key)[1].lstrip(".").lower()
    return key.startswith(SOURCE_PREFIX) and extension in IMAGE_EXTENSIONS


def make_variants(image: Image.Image) -> tuple[int, dict[int, bytes]]:
    """The upright width, and WebP bytes per target width narrower than it (never upscaled)."""
    upright = ImageOps.exif_transpose(image)
    if upright.mode not in ("RGB", "RGBA"):
        upright = upright.convert("RGBA" if "A" in upright.getbands() else "RGB")
    variants = {}
    for width in VARIANT_WIDTHS:
        if width >= upright.width:
            continue
        height = round(upright.height * width / upright.width)
        buf = io.BytesIO()
        upright.resize((width, height), Image.Resampling.LANCZOS).save(
            buf, format="WEBP", quality=WEBP_QUALITY
        )
        variants[width] = buf.getvalue()
    return upright.width, variants


def process(bucket: str, key: str, s3: S3Client) -> tuple[int, dict[int, str]]:
    """Write the variants of one object; returns its width and the key written per width."""
    if not is_source(key):
        logger.info("Skipped %s: not a post image", key)
        return 0, {}
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    with Image.open(io.BytesIO(body)) as image:
        original_width, variants = make_variants(image)
    written = {}
    for width, data in variants.items():
        target = variant_key(key, width)
        s3.put_object(
            Bucket=bucket,
            Key=target,
            Body=data,
            ContentType=VARIANT_CONTENT_TYPE,
            CacheControl=CACHE_CONTROL,
            ACL=PUBLIC_ACL,
        )
        written[width] = target
    logger.info("Wrote %d variants of %s", len(written), key)
    return original_width, written


def report(bucket: str, key: str, width: int, written: dict[int, str], sqs: SQSClient) -> None:
    """Tell the API which variants exist for one upload (nothing to tell: no message)."""
    if not written:
        return
    message = {
        RESULT_BUCKET: bucket,
        RESULT_SOURCE_KEY: key,
        RESULT_WIDTH: width,
        RESULT_VARIANTS: {str(w): target for w, target in written.items()},
    }
    sqs.send_message(QueueUrl=os.environ[RESULTS_QUEUE_URL_ENV], MessageBody=json.dumps(message))


def s3_objects(body: str) -> list[tuple[str, str]]:
    """(bucket, key) for each object in one queued S3 notification."""
    notification = json.loads(body)
    if notification.get("Event") == S3_TEST_EVENT:
        return []
    # Keys arrive URL-encoded (a space is "+").
    return [
        (record["s3"]["bucket"]["name"], unquote_plus(record["s3"]["object"]["key"]))
        for record in notification.get("Records", [])
    ]


def handle_message(body: str, s3: S3Client, sqs: SQSClient) -> None:
    """Resize and report every image in one queued notification."""
    for bucket, key in s3_objects(body):
        try:
            width, written = process(bucket, key, s3)
        except (Image.UnidentifiedImageError, Image.DecompressionBombError) as err:
            logger.warning("Skipped %s: %s", key, type(err).__name__)
            continue
        report(bucket, key, width, written, sqs)


def handler(event: dict[str, Any], context: object) -> dict[str, list[dict[str, str]]]:
    """One SQS batch -> variants for each message; returns the ones to retry.

    A message that raises (S3 or SQS unreachable, a malformed body) is named
    in batchItemFailures and comes back after the visibility timeout; the
    rest of the batch is deleted as done. Redoing a message is harmless:
    variant keys are derived from the source, so a retry overwrites the
    same objects with the same bytes.
    """
    failures = []
    for message in event.get("Records", []):
        try:
            handle_message(message["body"], _s3, _sqs)
        except Exception:  # every failure is retried by SQS, then parked and alarmed
            logger.exception("Failed message %s", message["messageId"])
            failures.append({"itemIdentifier": message["messageId"]})
    return {"batchItemFailures": failures}
