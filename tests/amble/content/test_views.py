"""HTTP endpoint tests. Reuses conftest fixtures (client + auth_header +
create_user + create_post) exactly like tests/amble/avatar/test_views.py."""

from app.amble.content.bindings import override_bindings
from app.amble.content.schema import EntityConfig


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


def test_get_returns_401_without_auth(client) -> None:
    response = client.get("/amble/content/some-entity")
    assert response.status_code in (401, 422)  # jwt-auth normalises upstream


def test_get_returns_404_for_unknown_entity(client, create_user, auth_header) -> None:
    override_bindings({})
    create_user(username="alice_view")
    response = client.get(
        "/amble/content/no-such",
        headers=auth_header("alice_view"),
    )
    assert response.status_code == 404


def test_get_returns_posts_for_content_backed_entity(
    client,
    create_user,
    create_post,
    auth_header,
) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["author_v"]),
        }
    )
    author = create_user(username="author_v")
    create_user(username="reader_v")
    create_post(user=author, text="Hello from the shop!")

    response = client.get("/amble/content/shop", headers=auth_header("reader_v"))
    assert response.status_code == 200
    body = response.json()
    assert body["entity_id"] == "shop"
    assert body["empty"] is False
    assert len(body["posts"]) == 1
    assert body["posts"][0]["author"] == "author_v"
    assert body["posts"][0]["text"] == "Hello from the shop!"


def test_get_returns_empty_when_no_posts_match(
    client,
    create_user,
    auth_header,
) -> None:
    override_bindings(
        {
            "shop": _persistent("shop", ["ghost_v"]),
        }
    )
    create_user(username="reader_v2")
    response = client.get("/amble/content/shop", headers=auth_header("reader_v2"))
    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is True
    assert body["posts"] == []
    assert body["next_cursor"] is None
