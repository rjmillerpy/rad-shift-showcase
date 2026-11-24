"""Tests for app/engagement/schema.py: the event contract between API and aggregator."""

import pytest
from pydantic import ValidationError

from app.engagement.schema import EVENT_WEIGHTS, SCHEMA_VERSION, PostEvent, PostEventType

VALID = {
    "event_id": "abc",
    "type": "post.liked",
    "post_id": 3,
    "user_id": 4,
    "occurred_at": 1_700_000_000.5,
}


def test_a_published_event_round_trips():
    event = PostEvent.new(PostEventType.SAVED, post_id=9, user_id=2)

    assert PostEvent.model_validate_json(event.model_dump_json()) == event
    assert event.schema_version == SCHEMA_VERSION
    assert len(event.event_id) == 32


def test_every_new_event_has_its_own_id():
    ids = {PostEvent.new(PostEventType.LIKED, 1, 1).event_id for _ in range(50)}

    assert len(ids) == 50


def test_an_anonymous_share_has_no_user():
    assert (
        PostEvent.model_validate({**VALID, "type": "post.shared", "user_id": None}).user_id is None
    )


def test_unknown_fields_are_ignored_so_producers_can_add_them():
    assert PostEvent.model_validate({**VALID, "client": "ios"}).post_id == 3


@pytest.mark.parametrize(
    "change",
    [
        {"type": "post.exploded"},
        {"post_id": 0},
        {"event_id": ""},
        {"event_id": "x" * 65},
        {"occurred_at": 0},
        {"schema_version": 0},
        {"user_id": 0},
    ],
    ids=["unknown-type", "no-post", "no-id", "long-id", "no-time", "bad-version", "bad-user"],
)
def test_anything_else_is_refused(change):
    with pytest.raises(ValidationError):
        PostEvent.model_validate({**VALID, **change})


def test_every_type_has_a_weight():
    assert set(EVENT_WEIGHTS) == set(PostEventType)


@pytest.mark.parametrize(
    "do,undo",
    [
        (PostEventType.LIKED, PostEventType.UNLIKED),
        (PostEventType.LAUGHED, PostEventType.UNLAUGHED),
        (PostEventType.SAVED, PostEventType.UNSAVED),
        (PostEventType.REPOSTED, PostEventType.UNREPOSTED),
    ],
)
def test_an_undo_cancels_its_action(do, undo):
    assert EVENT_WEIGHTS[do] + EVENT_WEIGHTS[undo] == 0
    assert EVENT_WEIGHTS[do] > 0
