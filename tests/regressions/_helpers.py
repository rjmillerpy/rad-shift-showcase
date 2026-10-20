"""Shared helpers for regression tests."""


def _signup(client, username, password="password123"):
    return client.post(
        "/auth/signup",
        json={"username": username, "password": password, "email": f"{username}@test.com"},
    )


def _login(client, username, password="password123"):
    res = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _setup(client, username):
    _signup(client, username)
    return _login(client, username)
