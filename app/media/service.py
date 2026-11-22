"""Record image variants on the posts that use each upload, from the results queue.

The Lambda resizes uploads in AWS and can't reach the API's database (it
runs on a laptop today), so it reports through a queue and this side
records. Delivery is at least once, and recording is idempotent: the same
message twice writes the same URLs.
"""

import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from pydantic import ValidationError
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.common.constants import S3_URL_TEMPLATE
from app.posts.models import PostModel

from .constants import (
    LOG_EVENT_BAD_MESSAGE,
    LOG_EVENT_NO_POST,
    LOG_EVENT_RECORDED,
    RECEIVE_MAX_MESSAGES,
    RECEIVE_WAIT_SECONDS,
)
from .schema import VariantResult

logger = logging.getLogger(__name__)

# boto3 ships no type information for its clients.
SQSClient = Any
# Opens a session for one message: app.common.db.SessionLocal in the app.
SessionFactory = Callable[[], AbstractContextManager[Session]]


def _url(bucket: str, key: str) -> str:
    return S3_URL_TEMPLATE.format(bucket=bucket, key=key)


def sizes(result: VariantResult) -> dict[str, str]:
    """Every width this image is available at, original included: {"480": url, ...}.

    The original is one of the candidates, so a browser showing the image
    wider than the largest variant still gets full resolution.
    """
    original = _url(result.bucket, result.source_key)
    urls = {width: _url(result.bucket, key) for width, key in result.variants.items()}
    return {**urls, str(result.width): original}


def record_variants(db: Session, result: VariantResult) -> int:
    """Store the sizes on every post showing this upload; returns how many."""
    original = _url(result.bucket, result.source_key)
    urls = sizes(result)
    # A post shows an upload as its first image (image_url) or in its list
    # (image_urls, JSON). Upload keys are ASCII (app/posts/uploads.py), so
    # the URL appears verbatim in the JSON text; the Python check below
    # drops a URL that merely contains this one.
    candidates = (
        db.query(PostModel)
        .filter(
            or_(
                PostModel.image_url == original,
                cast(PostModel.image_urls, String).contains(original),
            )
        )
        .all()
    )
    posts = [p for p in candidates if original in (p.image_urls or []) or p.image_url == original]
    for post in posts:
        # A new dict, not an in-place change: SQLAlchemy only notices a JSON
        # column changing when the attribute is reassigned. (The model uses
        # untyped Column(); mypy reads the attribute as the Column itself.)
        post.image_variants = {**(post.image_variants or {}), original: urls}  # type: ignore[assignment]
    db.commit()
    return len(posts)


def handle_message(body: str, session_factory: SessionFactory) -> None:
    """Record one message.

    A malformed message is logged and dropped: a retry would fail the same
    way. A database error propagates, so the message isn't deleted and comes
    back after the queue's visibility timeout.
    """
    try:
        result = VariantResult.model_validate(json.loads(body))
    except (ValueError, ValidationError):
        logger.warning(LOG_EVENT_BAD_MESSAGE, extra={"body_length": len(body)})
        return
    with session_factory() as db:
        count = record_variants(db, result)
    if count:
        logger.info(LOG_EVENT_RECORDED, extra={"source_key": result.source_key, "posts": count})
    else:
        # The post was deleted, or its creation failed after the upload.
        logger.info(LOG_EVENT_NO_POST, extra={"source_key": result.source_key})


def poll_once(
    sqs: SQSClient,
    queue_url: str,
    session_factory: SessionFactory,
    wait_seconds: int = RECEIVE_WAIT_SECONDS,
) -> int:
    """One long poll: record what arrives, delete what's done; returns messages handled."""
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=RECEIVE_MAX_MESSAGES,
        WaitTimeSeconds=wait_seconds,
    )
    messages = response.get("Messages", [])
    for message in messages:
        handle_message(message["Body"], session_factory)
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
    return len(messages)
