"""HTTP contract tests for /amble/avatar."""

from unittest.mock import patch

import pytest

from app.amble.avatar.constants import ERROR_MESSAGE_PERSISTENCE
from app.amble.avatar.service import AvatarPersistenceError

VALID_BODY = {
    "avatar": {
        "left": {"gender": "boy", "skin_tone": "warm", "hairstyle": "short", "clothing": "hoodie"},
        "right": {"gender": "girl", "skin_tone": "warm", "hairstyle": "long", "clothing": "dress"},
    }
}


# ── Auth ────────────────────────────────────────────────────────────────────
def test_get_without_token_is_401(client) -> None:
    response = client.get("/amble/avatar")
    assert response.status_code == 401


def test_put_without_token_is_401(client) -> None:
    response = client.put("/amble/avatar", json=VALID_BODY)
    assert response.status_code == 401


# ── Happy path ──────────────────────────────────────────────────────────────
def test_get_first_visit_returns_null_avatar(client, create_user, auth_header) -> None:
    create_user(username="ambler_view_a")
    response = client.get("/amble/avatar", headers=auth_header("ambler_view_a"))
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"avatar": None, "exists": False}


def test_put_then_get_round_trips(client, create_user, auth_header) -> None:
    create_user(username="ambler_view_b")
    headers = auth_header("ambler_view_b")

    put_response = client.put("/amble/avatar", headers=headers, json=VALID_BODY)
    assert put_response.status_code == 200
    assert put_response.json()["exists"] is True
    assert put_response.json()["avatar"] == VALID_BODY["avatar"]

    get_response = client.get("/amble/avatar", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json() == put_response.json()


def test_put_twice_overwrites(client, create_user, auth_header) -> None:
    create_user(username="ambler_view_c")
    headers = auth_header("ambler_view_c")
    client.put("/amble/avatar", headers=headers, json=VALID_BODY)

    alt = {
        "avatar": {
            "left": {
                "gender": "girl",
                "skin_tone": "cool",
                "hairstyle": "long",
                "clothing": "jacket",
            },
            "right": {
                "gender": "boy",
                "skin_tone": "warm",
                "hairstyle": "short",
                "clothing": "hoodie",
            },
        }
    }
    second = client.put("/amble/avatar", headers=headers, json=alt)
    assert second.status_code == 200
    assert second.json()["avatar"] == alt["avatar"]


# ── Validation (rule 5 — 422 for bad payloads) ──────────────────────────────
@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({}, id="empty-body"),
        pytest.param({"avatar": {}}, id="empty-avatar"),
        pytest.param({"avatar": {"left": VALID_BODY["avatar"]["left"]}}, id="missing-right"),
        pytest.param(
            {
                "avatar": {
                    "left": {**VALID_BODY["avatar"]["left"], "gender": "wizard"},
                    "right": VALID_BODY["avatar"]["right"],
                }
            },
            id="bad-gender",
        ),
        pytest.param(
            {
                "avatar": {
                    "left": {**VALID_BODY["avatar"]["left"], "skin_tone": ""},
                    "right": VALID_BODY["avatar"]["right"],
                }
            },
            id="empty-skin_tone",
        ),
        pytest.param(
            {
                "avatar": {
                    "left": {**VALID_BODY["avatar"]["left"], "skin_tone": "x" * 200},
                    "right": VALID_BODY["avatar"]["right"],
                }
            },
            id="oversized-skin_tone",
        ),
    ],
)
def test_put_validation_errors_return_422(client, create_user, auth_header, mutation: dict) -> None:
    create_user(username="ambler_view_v")
    response = client.put(
        "/amble/avatar",
        headers=auth_header("ambler_view_v"),
        json=mutation,
    )
    assert response.status_code == 422


# ── 500 path — the service raises a domain error, view masks internal detail ─
def test_persistence_failure_returns_safe_500(client, create_user, auth_header) -> None:
    create_user(username="ambler_view_e")
    with patch(
        "app.amble.avatar.views.upsert_avatar_for_user",
        side_effect=AvatarPersistenceError("underlying db exception"),
    ):
        response = client.put(
            "/amble/avatar",
            headers=auth_header("ambler_view_e"),
            json=VALID_BODY,
        )
    assert response.status_code == 500
    # User never sees the internal exception message (rule 10).
    assert response.json()["detail"] == ERROR_MESSAGE_PERSISTENCE
