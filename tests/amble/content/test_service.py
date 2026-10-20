"""Service-layer tests. Real DB rows via conftest fixtures; the binding
registry is overridden per-test via `override_bindings` so tests don't
depend on the shipped `entity-bindings.yaml`."""

import pytest

from app.amble.content.bindings import override_bindings
from app.amble.content.schema import (
    EntityConfig,
)
from app.amble.content.service import (
    UnknownEntityError,
    next_posts_for_entity,
    parse_cursor,
)


def _persistent_config(entity_id: str, usernames: list) -> EntityConfig:
    return EntityConfig.model_validate(
        {
            "entity_id": entity_id,
            "binding": {
                "kind": "persistent-identity",
                "usernames": usernames,
            },
        }
    )


def _category_config(entity_id: str, tags: list) -> EntityConfig:
    return EntityConfig.model_validate(
        {
            "entity_id": entity_id,
            "binding": {
                "kind": "category",
                "tags": tags,
            },
        }
    )


# ── parse_cursor unit tests ────────────────────────────────────────────────
def test_parse_cursor_defaults_to_zero_on_none() -> None:
    assert parse_cursor(None) == 0


def test_parse_cursor_accepts_numeric_string() -> None:
    assert parse_cursor("7") == 7


def test_parse_cursor_defaults_to_zero_on_junk() -> None:
    assert parse_cursor("junk") == 0
    assert parse_cursor("-5") == 0


# ── service-layer tests ────────────────────────────────────────────────────
def test_unknown_entity_raises(db_session, create_user) -> None:
    override_bindings({})
    user = create_user(username="viewer")
    with pytest.raises(UnknownEntityError):
        next_posts_for_entity(db_session, user, "no-such", None)


def test_persistent_identity_binding_returns_user_posts(
    db_session,
    create_user,
    create_post,
) -> None:
    override_bindings(
        {
            "shopkeeper": _persistent_config("shopkeeper", ["alice"]),
        }
    )
    author = create_user(username="alice")
    viewer = create_user(username="viewer1")
    create_post(user=author, text="one")
    create_post(user=author, text="two")

    response = next_posts_for_entity(db_session, viewer, "shopkeeper", None)
    assert response.empty is False
    assert len(response.posts) == 2
    assert {p.text for p in response.posts} == {"one", "two"}


def test_category_binding_matches_hashtag_in_text(
    db_session,
    create_user,
    create_post,
) -> None:
    override_bindings(
        {
            "cafe": _category_config("cafe", ["coffee"]),
        }
    )
    author = create_user(username="rando")
    viewer = create_user(username="viewer2")
    create_post(user=author, text="just some #coffee thoughts")
    create_post(user=author, text="unrelated post")

    response = next_posts_for_entity(db_session, viewer, "cafe", None)
    assert len(response.posts) == 1
    assert "#coffee" in response.posts[0].text


def test_empty_state_when_no_posts_match(
    db_session,
    create_user,
) -> None:
    override_bindings(
        {
            "shopkeeper": _persistent_config("shopkeeper", ["ghost"]),
        }
    )
    viewer = create_user(username="viewer3")

    response = next_posts_for_entity(db_session, viewer, "shopkeeper", None)
    assert response.empty is True
    assert response.posts == []
    assert response.next_cursor is None


def test_cursor_advances_and_signals_more(
    db_session,
    create_user,
    create_post,
) -> None:
    # Force page limit down to 2 by inserting 3 posts.
    override_bindings(
        {
            "shopkeeper": _persistent_config("shopkeeper", ["alice"]),
        }
    )
    author = create_user(username="alice")
    viewer = create_user(username="viewer4")
    for i in range(3):
        create_post(user=author, text=f"post-{i}")

    first = next_posts_for_entity(db_session, viewer, "shopkeeper", None, limit=2)
    assert len(first.posts) == 2
    assert first.next_cursor == "2"  # advanced past first two

    second = next_posts_for_entity(
        db_session,
        viewer,
        "shopkeeper",
        first.next_cursor,
        limit=2,
    )
    assert len(second.posts) == 1
    assert second.next_cursor is None
