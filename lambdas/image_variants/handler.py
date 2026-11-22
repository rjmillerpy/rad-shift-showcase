"""Lambda entry point: make web-sized variants of each new post image.

S3 calls this for every object created under posts/ with an image
extension (infra/media-pipeline/). For each one it writes a WebP per width
in VARIANT_WIDTHS, under variants/, keyed by the source: posts/a_1_0.jpg
becomes variants/posts/a_1_0-480.webp and -1280.webp. The original is never
changed, so a failure here costs a smaller image, never the post's.

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
    CACHE_CONTROL,
    IMAGE_EXTENSIONS,
    MAX_IMAGE_PIXELS,
    PUBLIC_ACL,
    S3_CONNECT_TIMEOUT_SECONDS,
    S3_MAX_ATTEMPTS,
    S3_READ_TIMEOUT_SECONDS,
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
_s3: S3Client = boto3.client(
    "s3",
    config=Config(
        connect_timeout=S3_CONNECT_TIMEOUT_SECONDS,
        read_timeout=S3_READ_TIMEOUT_SECONDS,
        retries={"max_attempts": S3_MAX_ATTEMPTS, "mode": "standard"},
    ),
)


def variant_key(source_key: str, width: int) -> str:
    """variants/<source key without extension>-<width>.webp"""
    stem, _ = posixpath.splitext(source_key)
    return f"{VARIANT_PREFIX}{stem}-{width}.webp"


def is_source(key: str) -> bool:
    """Whether a key is an image this function should resize."""
    extension = posixpath.splitext(key)[1].lstrip(".").lower()
    return key.startswith(SOURCE_PREFIX) and extension in IMAGE_EXTENSIONS


def make_variants(image: Image.Image) -> dict[int, bytes]:
    """WebP bytes per target width narrower than the image (never upscaled)."""
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
    return variants


def process(bucket: str, key: str, s3: S3Client) -> list[str]:
    """Write the variants of one object; returns the keys written."""
    if not is_source(key):
        logger.info("Skipped %s: not a post image", key)
        return []
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    with Image.open(io.BytesIO(body)) as image:
        variants = make_variants(image)
    written = []
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
        written.append(target)
    logger.info("Wrote %d variants of %s", len(written), key)
    return written


def handler(event: dict[str, Any], context: object) -> dict[str, list[str]]:
    """S3 event notification -> variants for every record in it.

    An exception fails the invocation, and S3's asynchronous invoke retries
    it twice; a broken image is logged and skipped instead, since retrying
    can't fix it.
    """
    written: list[str] = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        # Keys arrive URL-encoded (a space is "+").
        key = unquote_plus(record["s3"]["object"]["key"])
        try:
            written += process(bucket, key, _s3)
        except (Image.UnidentifiedImageError, Image.DecompressionBombError) as err:
            logger.warning("Skipped %s: %s", key, type(err).__name__)
    return {"written": written}
