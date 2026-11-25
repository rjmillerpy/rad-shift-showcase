"""app/ratelimit/deps.py: which policy a request falls under, who is counted,
and the 429 a client gets past its limit, through real endpoints."""

import pytest

from app.ratelimit.constants import LOGIN, SIGNUP, WIDGET_STORAGE, WRITE
from app.ratelimit.deps import policy_for


@pytest.fixture()
def limits_on(monkeypatch):
    """Limits on, and the clock held mid-window: a test making 60 requests
    could otherwise cross a minute boundary, where the window resets (the
    first version was flaky exactly so, caught by a slower CI run)."""
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "true")
    monkeypatch.setattr("app.ratelimit.deps.time.time", lambda: 1_800_000_030.0)


@pytest.mark.parametrize(
    ("method", "route", "policy"),
    [
        ("POST", "/auth/login", LOGIN),
        ("POST", "/auth/signup", SIGNUP),
        ("PUT", "/widgets/{widget_id}/storage/{key}", WIDGET_STORAGE),
        ("POST", "/posts/like/{post_id}", WRITE),
        ("DELETE", "/widgets/{widget_id}/like", WRITE),
        ("GET", "/posts/", None),
        ("GET", "/widgets/{widget_id}/storage/{key}", None),
    ],
)
def test_policy_for(method, route, policy):
    assert policy_for(method, route) == policy


def test_login_brute_force_gets_429_with_retry_after(client, create_user, limits_on):
    create_user(username="victim", password="right-password")
    statuses = [
        client.post("/auth/login", json={"username": "victim", "password": f"guess{i}"})
        for i in range(LOGIN.limit + 1)
    ]

    assert [r.status_code for r in statuses] == [401] * LOGIN.limit + [429]
    assert 0 < int(statuses[-1].headers["Retry-After"]) <= LOGIN.window_seconds


def test_writes_are_counted_per_user(client, create_user, create_post, auth_header, limits_on):
    post = create_post(user=create_user(username="author"))
    create_user(username="busy")
    create_user(username="calm")
    for _ in range(WRITE.limit):
        client.post(f"/posts/like/{post.id}", headers=auth_header("busy"))

    assert client.post(f"/posts/like/{post.id}", headers=auth_header("busy")).status_code == 429
    assert client.post(f"/posts/like/{post.id}", headers=auth_header("calm")).status_code == 200


def test_reads_are_not_limited(client, limits_on):
    assert all(client.get("/posts/").status_code == 200 for _ in range(WRITE.limit + 5))


def test_switched_off_nothing_is_counted(client, create_user):
    create_user(username="victim", password="right-password")
    statuses = {
        client.post("/auth/login", json={"username": "victim", "password": "x"}).status_code
        for _ in range(LOGIN.limit + 1)
    }
    assert statuses == {401}
