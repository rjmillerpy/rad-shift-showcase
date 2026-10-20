"""Shared helpers for integration tests."""

import json


def _signup(client, username="alice", password="password123"):
    return client.post(
        "/auth/signup",
        json={"username": username, "password": password, "email": f"{username}@test.com"},
    )


def _login(client, username="alice", password="password123"):
    res = client.post("/auth/login", json={"username": username, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_post(client, headers, text="Test post", **kwargs):
    data = {
        "text": text,
        "post_metadata": json.dumps(kwargs.get("metadata", {})),
        "is_draft": str(kwargs.get("is_draft", False)).lower(),
    }
    if kwargs.get("parent_post_id"):
        data["parent_post_id"] = str(kwargs["parent_post_id"])
    if kwargs.get("is_reply"):
        data["is_reply"] = "true"
    return client.post("/posts/add", data=data, headers=headers)
