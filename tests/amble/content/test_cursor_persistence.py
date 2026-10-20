"""Phase 1.4d — cross-session cursor persistence (D2).

The service persists (user, entity) offset to DB so re-visits pick up where
the player left off. Two calls in a row without a client cursor should
advance forward; explicit client cursor still forces the offset.
"""

from app.amble.content.bindings import override_bindings
from app.amble.content.models import AmbleContentCursor
from app.amble.content.schema import EntityConfig
from app.amble.content.service import next_posts_for_entity


def _persistent(entity_id: str, usernames: list) -> EntityConfig:
    return EntityConfig.model_validate(
        {
            "entity_id": entity_id,
            "binding": {
                "kind": "persistent-identity",
                "usernames": usernames,
            },
        }
    )


def _cursor_row(db, user_id, entity_id):
    return (
        db.query(AmbleContentCursor)
        .filter(
            AmbleContentCursor.user_id == user_id,
            AmbleContentCursor.entity_id == entity_id,
        )
        .one_or_none()
    )


def test_first_visit_writes_cursor(db_session, create_user, create_post) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["author_a"]),
        }
    )
    author = create_user(username="author_a")
    viewer = create_user(username="viewer_a")
    for i in range(3):
        create_post(user=author, text=f"post-{i}")

    response = next_posts_for_entity(db_session, viewer, "shop", None, limit=2)
    assert len(response.posts) == 2

    row = _cursor_row(db_session, viewer.id, "shop")
    assert row is not None
    assert row.offset_val == 2


def test_second_visit_resumes_from_persisted_cursor(
    db_session,
    create_user,
    create_post,
) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["author_b"]),
        }
    )
    author = create_user(username="author_b")
    viewer = create_user(username="viewer_b")
    for i in range(4):
        create_post(user=author, text=f"post-{i}")

    # First "visit" — advances to offset 2.
    first = next_posts_for_entity(db_session, viewer, "shop", None, limit=2)
    assert first.next_cursor == "2"

    # Second "visit" with no client cursor — server should resume from 2.
    second = next_posts_for_entity(db_session, viewer, "shop", None, limit=2)
    assert len(second.posts) == 2
    # Cursor should now be at 4 (exhausted, next_cursor=None).
    assert second.next_cursor is None

    row = _cursor_row(db_session, viewer.id, "shop")
    assert row.offset_val == 4


def test_explicit_client_cursor_overrides_persisted(
    db_session,
    create_user,
    create_post,
) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["author_c"]),
        }
    )
    author = create_user(username="author_c")
    viewer = create_user(username="viewer_c")
    for i in range(5):
        create_post(user=author, text=f"post-{i}")

    # Prime the persisted cursor to 3.
    next_posts_for_entity(db_session, viewer, "shop", None, limit=3)
    row = _cursor_row(db_session, viewer.id, "shop")
    assert row.offset_val == 3

    # Client explicitly resends "0" — force restart from the top.
    reset = next_posts_for_entity(db_session, viewer, "shop", "0", limit=2)
    assert len(reset.posts) == 2
    # Cursor persistence still writes forward from the client's offset.
    assert _cursor_row(db_session, viewer.id, "shop").offset_val == 2


def test_empty_state_does_not_advance_cursor(
    db_session,
    create_user,
) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["ghost"]),
        }
    )
    viewer = create_user(username="viewer_d")

    response = next_posts_for_entity(db_session, viewer, "shop", None, limit=2)
    assert response.empty is True
    # No posts returned → no cursor written yet (nothing to advance past).
    assert _cursor_row(db_session, viewer.id, "shop") is None


def test_two_users_have_independent_cursors(
    db_session,
    create_user,
    create_post,
) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["author_e"]),
        }
    )
    author = create_user(username="author_e")
    viewer_a = create_user(username="viewer_e_a")
    viewer_b = create_user(username="viewer_e_b")
    for i in range(4):
        create_post(user=author, text=f"post-{i}")

    # A advances to 2.
    next_posts_for_entity(db_session, viewer_a, "shop", None, limit=2)
    # B advances to 3.
    next_posts_for_entity(db_session, viewer_b, "shop", None, limit=3)

    row_a = _cursor_row(db_session, viewer_a.id, "shop")
    row_b = _cursor_row(db_session, viewer_b.id, "shop")
    assert row_a.offset_val == 2
    assert row_b.offset_val == 3


def test_exhausted_feed_returns_empty_with_persisted_offset_intact(
    db_session,
    create_user,
    create_post,
) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["author_f"]),
        }
    )
    author = create_user(username="author_f")
    viewer = create_user(username="viewer_f")
    create_post(user=author, text="only-post")

    # First fetch consumes the one post.
    first = next_posts_for_entity(db_session, viewer, "shop", None, limit=2)
    assert len(first.posts) == 1
    assert first.next_cursor is None

    # Second fetch: no more posts. Empty state (CONTENT-05).
    second = next_posts_for_entity(db_session, viewer, "shop", None, limit=2)
    assert second.empty is True
    assert second.posts == []
    # Persisted cursor stays at 1 — didn't rewind, didn't advance.
    assert _cursor_row(db_session, viewer.id, "shop").offset_val == 1
