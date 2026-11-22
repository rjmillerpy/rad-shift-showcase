"""Lambda entry point: make web-sized variants of one post image.

A Step Functions workflow (infra/media-pipeline/state_machine.asl.json)
calls this once per uploaded image with {"bucket", "key"}. It writes a WebP
per width in VARIANT_WIDTHS, under variants/, keyed by the source:
posts/a_1_0.jpg becomes variants/posts/a_1_0-480.webp and -1280.webp. The
original is never changed, so a failure here costs a smaller image, never
the post's.

It returns the result and the workflow does the rest: reporting it to the
API's queue, retrying when this raises, and parking what keeps failing in
the dead-letter queue. So this function only resizes: an error raises, and
a broken image returns {"skipped": ...} because retrying can't fix it.

Runs on AWS's python3.12 runtime, which provides boto3; the deployment zip
carries Pillow and this package at the same path as in the repository, so
the handler is lambdas.image_variants.handler.handler in both
(scripts/build_lambda.sh).
"""

from __future__ import annotations

import io
import logging
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
    RESULT_SKIPPED,
    RESULT_SOURCE_KEY,
    RESULT_VARIANTS,
    RESULT_WIDTH,
    SOURCE_PREFIX,
    VARIANT_CONTENT_TYPE,
    VARIANT_PREFIX,
    VARIANT_WIDTHS,
    WEBP_QUALITY,
)

# boto3 ships no type information for its clients.
S3Client = Any

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


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """{"bucket", "key"} from the workflow -> the result for the API's queue.

    {bucket, source_key, width, variants} when variants were written, else
    {"skipped": why}: not a post image, too narrow for any variant, or an
    unreadable file. Anything else raises, for the workflow to retry.
    """
    bucket = event["bucket"]
    # The workflow passes the key as S3's notification has it: URL-encoded
    # (a space is "+").
    key = unquote_plus(event["key"])
    try:
        width, written = process(bucket, key, _s3)
    except (Image.UnidentifiedImageError, Image.DecompressionBombError) as err:
        logger.warning("Skipped %s: %s", key, type(err).__name__)
        return {RESULT_SKIPPED: type(err).__name__}
    if not written:
        return {RESULT_SKIPPED: "no variants"}
    return {
        RESULT_BUCKET: bucket,
        RESULT_SOURCE_KEY: key,
        RESULT_WIDTH: width,
        RESULT_VARIANTS: {str(w): target for w, target in written.items()},
    }
