"""Service-layer tests. Real DB rows via conftest; only SQL errors are
simulated (external boundary) so we can exercise the failure path."""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from app.amble.avatar.schema import AvatarSchema
from app.amble.avatar.service import (
    AvatarPersistenceError,
    get_avatar_for_user,
    upsert_avatar_for_user,
)

SAMPLE = AvatarSchema.model_validate(
    {
        "left": {"gender": "boy", "skin_tone": "warm", "hairstyle": "short", "clothing": "hoodie"},
        "right": {"gender": "girl", "skin_tone": "warm", "hairstyle": "long", "clothing": "dress"},
    }
)

SAMPLE_ALT = AvatarSchema.model_validate(
    {
        "left": {"gender": "girl", "skin_tone": "cool", "hairstyle": "long", "clothing": "jacket"},
        "right": {"gender": "boy", "skin_tone": "warm", "hairstyle": "short", "clothing": "hoodie"},
    }
)


def test_get_returns_none_when_no_row(db_session, create_user) -> None:
    user = create_user(username="svc_a")
    assert get_avatar_for_user(db_session, user.id) is None


def test_upsert_insert_then_get_round_trips(db_session, create_user) -> None:
    user = create_user(username="svc_b")
    saved = upsert_avatar_for_user(db_session, user.id, SAMPLE)
    assert saved == SAMPLE
    fetched = get_avatar_for_user(db_session, user.id)
    assert fetched == SAMPLE


def test_upsert_update_path_overwrites_existing(db_session, create_user) -> None:
    user = create_user(username="svc_c")
    upsert_avatar_for_user(db_session, user.id, SAMPLE)
    upsert_avatar_for_user(db_session, user.id, SAMPLE_ALT)
    fetched = get_avatar_for_user(db_session, user.id)
    assert fetched == SAMPLE_ALT


def test_upsert_wraps_sqlalchemy_errors_in_domain_error(db_session, create_user) -> None:
    user = create_user(username="svc_d")
    with (
        patch(
            "app.amble.avatar.service.Session.commit",
            side_effect=OperationalError("stmt", {}, Exception("db down")),
        ),
        pytest.raises(AvatarPersistenceError),
    ):
        upsert_avatar_for_user(db_session, user.id, SAMPLE)
