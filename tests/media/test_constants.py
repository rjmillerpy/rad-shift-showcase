"""Tests for app/media/constants.py: it must read what the Lambda writes."""

from app.media import constants
from lambdas.image_variants import constants as lambda_constants


def test_message_keys_match_the_lambdas():
    names = ("RESULT_BUCKET", "RESULT_SOURCE_KEY", "RESULT_VARIANTS", "RESULT_WIDTH")
    assert [getattr(constants, n) for n in names] == [getattr(lambda_constants, n) for n in names]


def test_the_read_timeout_outlasts_the_long_poll():
    assert constants.SQS_READ_TIMEOUT_SECONDS > constants.RECEIVE_WAIT_SECONDS


def test_stopping_never_holds_up_a_container_stop():
    """Docker sends SIGKILL 10 s after SIGTERM."""
    assert constants.WORKER_JOIN_TIMEOUT_SECONDS < 10


def test_sqs_limits():
    # SQS caps a receive at 10 messages and a long poll at 20 s.
    assert 1 <= constants.RECEIVE_MAX_MESSAGES <= 10
    assert 1 <= constants.RECEIVE_WAIT_SECONDS <= 20
