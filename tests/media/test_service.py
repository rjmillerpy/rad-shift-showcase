"""Tests for app/media/service.py: real posts in the test DB, moto's SQS."""

import json
import logging

import pytest
from sqlalchemy.exc import OperationalError

from app.media.constants import LOG_EVENT_BAD_MESSAGE, LOG_EVENT_NO_POST, LOG_EVENT_RECORDED
from app.media.schema import VariantResult
from app.media.service import handle_message, poll_once, record_variants

from .conftest import result_for, url


@pytest.fixture()
def post_with_images(db_session, create_user, create_post):
    def _make(*keys: str):
        post = create_post(create_user("alice"))
        post.image_url = url(keys[0])
        post.image_urls = [url(k) for k in keys]
        db_session.commit()
        return post

    return _make


def _result(key: str, widths=(480, 1280)) -> VariantResult:
    return VariantResult.model_validate(result_for(key, widths))


class TestRecordVariants:
    def test_variant_urls_are_stored_against_the_original(self, db_session, post_with_images):
        post = post_with_images("posts/alice_1_0.jpg")
        assert record_variants(db_session, _result("posts/alice_1_0.jpg")) == 1
        db_session.refresh(post)
        assert post.image_variants == {
            url("posts/alice_1_0.jpg"): {
                "480": url("variants/posts/alice_1_0-480.webp"),
                "1280": url("variants/posts/alice_1_0-1280.webp"),
                "2000": url("posts/alice_1_0.jpg"),  # the original is a candidate too
            }
        }

    def test_each_image_of_a_multi_image_post_is_kept(self, db_session, post_with_images):
        post = post_with_images("posts/alice_1_0.jpg", "posts/alice_1_1.jpg")
        record_variants(db_session, _result("posts/alice_1_0.jpg"))
        record_variants(db_session, _result("posts/alice_1_1.jpg", (480,)))
        db_session.refresh(post)
        assert set(post.image_variants) == {url("posts/alice_1_0.jpg"), url("posts/alice_1_1.jpg")}

    def test_recording_twice_changes_nothing(self, db_session, post_with_images):
        """SQS delivers at least once."""
        post = post_with_images("posts/alice_1_0.jpg")
        record_variants(db_session, _result("posts/alice_1_0.jpg"))
        first = dict(post.image_variants)
        record_variants(db_session, _result("posts/alice_1_0.jpg"))
        db_session.refresh(post)
        assert post.image_variants == first

    def test_a_url_that_only_contains_this_one_is_not_matched(self, db_session, post_with_images):
        other = post_with_images("posts/alice_1_0.jpg.bak")
        assert record_variants(db_session, _result("posts/alice_1_0.jpg")) == 0
        db_session.refresh(other)
        assert other.image_variants is None

    def test_no_post_uses_the_upload(self, db_session):
        assert record_variants(db_session, _result("posts/gone_1_0.jpg")) == 0


class TestHandleMessage:
    def test_a_result_is_recorded_and_logged(
        self, db_session, session_factory, post_with_images, caplog
    ):
        post = post_with_images("posts/alice_1_0.jpg")
        with caplog.at_level(logging.INFO):
            handle_message(json.dumps(result_for("posts/alice_1_0.jpg")), session_factory)
        db_session.refresh(post)
        assert post.image_variants
        assert any(r.getMessage() == LOG_EVENT_RECORDED and r.posts == 1 for r in caplog.records)

    def test_a_result_for_a_deleted_post_is_logged(self, session_factory, caplog):
        with caplog.at_level(logging.INFO):
            handle_message(json.dumps(result_for("posts/gone_1_0.jpg")), session_factory)
        assert any(r.getMessage() == LOG_EVENT_NO_POST for r in caplog.records)

    @pytest.mark.parametrize("body", ["not json", "[]", json.dumps({"bucket": "b"})])
    def test_a_malformed_message_is_logged_and_dropped(self, session_factory, caplog, body):
        handle_message(body, session_factory)
        (record,) = [r for r in caplog.records if r.getMessage() == LOG_EVENT_BAD_MESSAGE]
        assert record.body_length == len(body)


class TestPollOnce:
    def test_handled_messages_are_deleted(
        self, results_queue, send_result, session_factory, post_with_images
    ):
        sqs, queue_url = results_queue
        post_with_images("posts/alice_1_0.jpg")
        send_result(result_for("posts/alice_1_0.jpg"))
        send_result("not json")
        assert poll_once(sqs, queue_url, session_factory) == 2
        attributes = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["All"])[
            "Attributes"
        ]
        assert attributes["ApproximateNumberOfMessages"] == "0"
        assert attributes["ApproximateNumberOfMessagesNotVisible"] == "0"

    def test_a_database_error_leaves_the_message_for_a_retry(self, results_queue, send_result):
        sqs, queue_url = results_queue
        send_result(result_for("posts/alice_1_0.jpg"))

        def broken_database():
            raise OperationalError("SELECT 1", {}, Exception("database is down"))

        with pytest.raises(OperationalError):
            poll_once(sqs, queue_url, broken_database)
        attributes = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["All"])[
            "Attributes"
        ]
        assert attributes["ApproximateNumberOfMessagesNotVisible"] == "1"

    def test_an_empty_queue(self, results_queue, session_factory):
        sqs, queue_url = results_queue
        assert poll_once(sqs, queue_url, session_factory, wait_seconds=0) == 0
