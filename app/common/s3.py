"""S3 upload/download helpers with explicit boto3 timeouts (rule 67)."""

import json
import logging
import os
from typing import IO

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from app.common.constants import (
    S3_CONNECT_TIMEOUT_SECONDS,
    S3_PUBLIC_ACL,
    S3_READ_TIMEOUT_SECONDS,
    S3_URL_TEMPLATE,
)

load_dotenv()
logger = logging.getLogger(__name__)


BUCKET_NAME: str | None = os.getenv("S3_BUCKET_NAME")
# The AWS account that must own the bucket. S3 refuses the request if anyone
# else does, so if the bucket were ever deleted and its name taken by another
# account ("bucket sniping"), uploads fail instead of landing in their bucket.
# ECS sets it to the deploying account (infra/ecs.tf). Unset: no check.
EXPECTED_BUCKET_OWNER: str | None = os.getenv("S3_EXPECTED_BUCKET_OWNER")


def _owner_args() -> dict[str, str]:
    return {"ExpectedBucketOwner": EXPECTED_BUCKET_OWNER} if EXPECTED_BUCKET_OWNER else {}


_boto_config = BotoConfig(
    connect_timeout=S3_CONNECT_TIMEOUT_SECONDS,
    read_timeout=S3_READ_TIMEOUT_SECONDS,
)
s3_client = boto3.client("s3", config=_boto_config)


def upload_json_data_to_s3(data: dict, file_key: str = "my_data.json") -> None:
    """Upload a dict as JSON to S3."""
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=file_key,
        Body=json.dumps(data),
        ContentType="application/json",
        **_owner_args(),
    )


def upload_to_s3(
    file_path: str,
    bucket_name: str | None = None,
    s3_key: str = "",
) -> None:
    """Upload a local file to S3. Errors are logged and swallowed (best-effort)."""
    bucket = bucket_name or BUCKET_NAME
    try:
        s3_client.upload_file(file_path, bucket, s3_key, ExtraArgs=_owner_args())
    except (BotoCoreError, ClientError) as exc:
        logger.error("Error uploading file %s to s3://%s/%s: %s", file_path, bucket, s3_key, exc)
        return
    logger.info("Uploaded %s to s3://%s/%s", file_path, bucket, s3_key)


def download_from_s3(
    bucket_name: str | None = None,
    s3_key: str = "",
    download_path: str = "download.txt",
) -> None:
    """Download an S3 object to a local path. Errors are logged and swallowed."""
    bucket = bucket_name or BUCKET_NAME
    try:
        s3_client.download_file(bucket, s3_key, download_path, ExtraArgs=_owner_args())
    except (BotoCoreError, ClientError) as exc:
        logger.error("Error downloading s3://%s/%s: %s", bucket, s3_key, exc)
        return
    logger.info("Downloaded s3://%s/%s to %s", bucket, s3_key, download_path)


def upload_fileobj_to_s3(
    fileobj: IO[bytes],
    s3_key: str,
    content_type: str = "image/jpeg",
) -> str:
    """Upload an in-memory file and return the public S3 URL.

    Re-raises boto errors so callers can convert to a domain-level failure.
    """
    try:
        s3_client.upload_fileobj(
            Fileobj=fileobj,
            Bucket=BUCKET_NAME,
            Key=s3_key,
            ExtraArgs={"ContentType": content_type, "ACL": S3_PUBLIC_ACL, **_owner_args()},
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("Error uploading fileobj to S3 key=%s: %s", s3_key, exc)
        raise
    return S3_URL_TEMPLATE.format(bucket=BUCKET_NAME, key=s3_key)
