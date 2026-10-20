"""Tests for app/common/constants.py — invariants on shared constants."""

from app.common import constants


class TestNumericConstants:
    def test_email_timeout_bounded(self):
        assert 1 <= constants.EMAIL_TIMEOUT_SECONDS <= 60

    def test_s3_timeouts_positive(self):
        assert constants.S3_CONNECT_TIMEOUT_SECONDS > 0
        assert constants.S3_READ_TIMEOUT_SECONDS > 0

    def test_s3_read_at_least_as_long_as_connect(self):
        assert constants.S3_READ_TIMEOUT_SECONDS >= constants.S3_CONNECT_TIMEOUT_SECONDS


class TestUrlAndAcl:
    def test_s3_url_template_has_placeholders(self):
        assert "{bucket}" in constants.S3_URL_TEMPLATE
        assert "{key}" in constants.S3_URL_TEMPLATE

    def test_s3_public_acl(self):
        assert constants.S3_PUBLIC_ACL == "public-read"


class TestDefaults:
    def test_default_origin_is_local(self):
        assert constants.DEFAULT_ALLOWED_ORIGIN.startswith("http://")

    def test_default_from_email_looks_like_email(self):
        assert "@" in constants.DEFAULT_FROM_EMAIL


class TestLogFormat:
    def test_log_format_has_asctime_and_levelname(self):
        assert "%(asctime)s" in constants.LOG_FORMAT
        assert "%(levelname)s" in constants.LOG_FORMAT
