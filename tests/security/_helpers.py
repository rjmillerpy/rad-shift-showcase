"""Shared helpers for security-focused tests."""


def _signup(client, username="secuser", password="password123"):
    return client.post(
        "/auth/signup",
        json={"username": username, "password": password, "email": f"{username}@test.com"},
    )


def _login(client, username="secuser", password="password123"):
    res = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _setup(client, username="secuser"):
    _signup(client, username)
    return _login(client, username)


def _make_post(client, headers, text="Post", **kw):
    data = {
        "text": text,
        "post_metadata": kw.get("metadata", "{}"),
        "is_draft": str(kw.get("is_draft", False)).lower(),
    }
    if kw.get("parent_post_id"):
        data["parent_post_id"] = str(kw["parent_post_id"])
    if kw.get("is_reply"):
        data["is_reply"] = "true"
    return client.post("/posts/add", data=data, headers=headers)
