"""Tests for app/common/s3.py — upload/download helpers with timeouts."""

import io

import pytest
from botocore.exceptions import ClientError


class TestBotoClientConfig:
    def test_boto_config_uses_configured_timeouts(self):
        """Verify rule 67: the BotoConfig used to build s3_client has explicit timeouts."""
        from app.common.constants import (
            S3_CONNECT_TIMEOUT_SECONDS,
            S3_READ_TIMEOUT_SECONDS,
        )
        from app.common.s3 import _boto_config

        assert _boto_config.connect_timeout == S3_CONNECT_TIMEOUT_SECONDS
        assert _boto_config.read_timeout == S3_READ_TIMEOUT_SECONDS


class TestUploadToS3:
    def test_delegates_to_client(self):
        from app.common.s3 import s3_client, upload_to_s3

        s3_client.upload_file.reset_mock()
        s3_client.upload_file.side_effect = None
        upload_to_s3("/tmp/test.txt", s3_key="key.txt")
        s3_client.upload_file.assert_called_once()

    def test_uses_default_bucket_when_not_specified(self):
        from app.common.s3 import BUCKET_NAME, s3_client, upload_to_s3

        s3_client.upload_file.reset_mock()
        s3_client.upload_file.side_effect = None
        upload_to_s3("/tmp/test.txt", s3_key="key.txt")
        assert s3_client.upload_file.call_args[0][1] == BUCKET_NAME

    def test_custom_bucket_overrides_default(self):
        from app.common.s3 import s3_client, upload_to_s3

        s3_client.upload_file.reset_mock()
        s3_client.upload_file.side_effect = None
        upload_to_s3("/tmp/test.txt", bucket_name="custom-bucket", s3_key="key.txt")
        assert s3_client.upload_file.call_args[0][1] == "custom-bucket"

    def test_boto_error_logged_not_raised(self):
        from app.common.s3 import s3_client, upload_to_s3

        s3_client.upload_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "gone"}},
            "upload_file",
        )
        try:
            upload_to_s3("/tmp/x.txt", s3_key="k.txt")  # must not raise
        finally:
            s3_client.upload_file.side_effect = None


class TestDownloadFromS3:
    def test_delegates_to_client(self):
        from app.common.s3 import download_from_s3, s3_client

        s3_client.download_file.reset_mock()
        s3_client.download_file.side_effect = None
        download_from_s3(s3_key="k", download_path="/tmp/x")
        s3_client.download_file.assert_called_once()

    def test_custom_bucket_overrides_default(self):
        from app.common.s3 import download_from_s3, s3_client

        s3_client.download_file.reset_mock()
        s3_client.download_file.side_effect = None
        download_from_s3(bucket_name="other", s3_key="k")
        assert s3_client.download_file.call_args[0][0] == "other"

    def test_boto_error_logged_not_raised(self):
        from app.common.s3 import download_from_s3, s3_client

        s3_client.download_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "gone"}},
            "download_file",
        )
        try:
            download_from_s3(s3_key="k")  # must not raise
        finally:
            s3_client.download_file.side_effect = None


class TestUploadJsonData:
    def test_delegates_to_put_object(self):
        from app.common.s3 import s3_client, upload_json_data_to_s3

        s3_client.put_object.reset_mock()
        s3_client.put_object.side_effect = None
        upload_json_data_to_s3({"key": "value"}, "data.json")
        s3_client.put_object.assert_called_once()

    def test_puts_json_content_type(self):
        from app.common.s3 import s3_client, upload_json_data_to_s3

        s3_client.put_object.reset_mock()
        s3_client.put_object.side_effect = None
        upload_json_data_to_s3({"a": 1}, "d.json")
        kwargs = s3_client.put_object.call_args.kwargs
        assert kwargs["ContentType"] == "application/json"


class TestUploadFileobjToS3:
    def test_returns_url_string_via_conftest_patch(self):
        """The global conftest patch stubs the URL. Just verify it's used."""
        from app.common.s3 import upload_fileobj_to_s3

        url = upload_fileobj_to_s3(io.BytesIO(b"data"), "test/key.jpg")
        assert isinstance(url, str)
        assert "test/key.jpg" in url

    @pytest.mark.parametrize(
        "s3_key,content_type",
        [
            ("images/photo.jpg", "image/jpeg"),
            ("images/pic.png", "image/png"),
            ("docs/file.pdf", "application/pdf"),
        ],
        ids=["jpeg", "png", "pdf"],
    )
    def test_various_content_types(self, s3_key, content_type):
        from app.common.s3 import upload_fileobj_to_s3

        url = upload_fileobj_to_s3(io.BytesIO(b"x"), s3_key, content_type=content_type)
        assert s3_key in url

    def test_the_real_function_uploads_and_returns_the_public_url(self):
        from app.common.s3 import BUCKET_NAME, s3_client
        from tests.conftest import REAL_UPLOAD_FILEOBJ_TO_S3

        s3_client.upload_fileobj.reset_mock()
        s3_client.upload_fileobj.side_effect = None
        url = REAL_UPLOAD_FILEOBJ_TO_S3(io.BytesIO(b"x"), "a/b.png", content_type="image/png")
        assert s3_client.upload_fileobj.call_args.kwargs["Key"] == "a/b.png"
        assert BUCKET_NAME in url and url.endswith("a/b.png")

    def test_the_real_function_re_raises_boto_errors(self):
        from app.common.s3 import s3_client
        from tests.conftest import REAL_UPLOAD_FILEOBJ_TO_S3

        s3_client.upload_fileobj.side_effect = ClientError({"Error": {"Code": "403"}}, "PutObject")
        try:
            with pytest.raises(ClientError):
                REAL_UPLOAD_FILEOBJ_TO_S3(io.BytesIO(b"x"), "a/b.png")
        finally:
            s3_client.upload_fileobj.side_effect = None


OWNER = "123456789012"


def _owner_calls(s3_client):
    """Run every helper once; the owner each one sent to S3 (None: not sent)."""
    from app.common import s3
    from tests.conftest import REAL_UPLOAD_FILEOBJ_TO_S3

    for method in ("put_object", "upload_file", "download_file", "upload_fileobj"):
        getattr(s3_client, method).reset_mock()
        getattr(s3_client, method).side_effect = None
    s3.upload_json_data_to_s3({"a": 1}, "k.json")
    s3.upload_to_s3("/tmp/f.txt", s3_key="k.txt")
    s3.download_from_s3(s3_key="k.txt", download_path="/tmp/f.txt")
    REAL_UPLOAD_FILEOBJ_TO_S3(io.BytesIO(b"x"), "k.jpg")
    return {
        "put_object": s3_client.put_object.call_args.kwargs.get("ExpectedBucketOwner"),
        "upload_file": s3_client.upload_file.call_args.kwargs["ExtraArgs"].get(
            "ExpectedBucketOwner"
        ),
        "download_file": s3_client.download_file.call_args.kwargs["ExtraArgs"].get(
            "ExpectedBucketOwner"
        ),
        "upload_fileobj": s3_client.upload_fileobj.call_args.kwargs["ExtraArgs"].get(
            "ExpectedBucketOwner"
        ),
    }


class TestExpectedBucketOwner:
    """Every S3 call names the account that must own the bucket (bucket sniping)."""

    def test_every_call_sends_the_configured_owner(self, monkeypatch):
        from app.common import s3

        monkeypatch.setattr(s3, "EXPECTED_BUCKET_OWNER", OWNER)
        assert _owner_calls(s3.s3_client) == dict.fromkeys(
            ("put_object", "upload_file", "download_file", "upload_fileobj"), OWNER
        )

    def test_unset_sends_no_owner(self, monkeypatch):
        from app.common import s3

        monkeypatch.setattr(s3, "EXPECTED_BUCKET_OWNER", None)
        assert set(_owner_calls(s3.s3_client).values()) == {None}

    def test_uploads_keep_their_content_type_and_acl(self, monkeypatch):
        from app.common import s3

        monkeypatch.setattr(s3, "EXPECTED_BUCKET_OWNER", OWNER)
        _owner_calls(s3.s3_client)
        extra = s3.s3_client.upload_fileobj.call_args.kwargs["ExtraArgs"]
        assert extra == {
            "ContentType": "image/jpeg",
            "ACL": s3.S3_PUBLIC_ACL,
            "ExpectedBucketOwner": OWNER,
        }
