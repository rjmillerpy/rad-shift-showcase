"""
Smoke tests — quick sanity checks that the application boots and
critical paths work end-to-end. Run these first to catch fundamental
breakage before the full test suite.

These should be FAST (<10s total) and test only the happy path.
"""


def _signup(client, username="smoke_user"):
    return client.post(
        "/auth/signup",
        json={
            "username": username,
            "password": "password123",
            "email": f"{username}@test.com",
        },
    )


def _login(client, username="smoke_user"):
    res = client.post("/auth/login", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


class TestSmokeBackend:
    """Verify the app boots and all critical endpoints respond."""

    def test_app_boots(self, client):
        """FastAPI app starts and responds to requests."""
        res = client.get("/posts/")
        assert res.status_code == 200

    def test_signup_login_flow(self, client):
        """User can sign up and log in."""
        res = _signup(client)
        assert res.status_code == 200

        res = client.post("/auth/login", json={"username": "smoke_user", "password": "password123"})
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_create_and_read_post(self, client):
        """User can create a post and see it in the feed."""
        h = (_signup(client, "smoke_poster"), _login(client, "smoke_poster"))[1]

        res = client.post(
            "/posts/add",
            data={"text": "Smoke test post", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        assert res.status_code == 200

        res = client.get("/posts/", headers=h)
        assert res.status_code == 200
        assert any(p["text"] == "Smoke test post" for p in res.json()["posts"])

    def test_like_post(self, client):
        """User can like a post."""
        _signup(client, "smoke_liker")
        h = _login(client, "smoke_liker")
        client.post(
            "/posts/add",
            data={"text": "Likeable", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        res = client.post(f"/posts/like/{pid}", headers=h)
        assert res.status_code == 200
        assert res.json()["action"] == "liked"

    def test_follow_user(self, client):
        """User can follow another user."""
        _signup(client, "smoke_target")
        _signup(client, "smoke_follower")
        h = _login(client, "smoke_follower")

        res = client.post("/follow/smoke_target", headers=h)
        assert res.status_code == 200

    def test_profile_accessible(self, client):
        """Profile endpoint works."""
        _signup(client, "smoke_profile")
        h = _login(client, "smoke_profile")

        res = client.get("/profile/me", headers=h)
        assert res.status_code == 200
        assert res.json()["username"] == "smoke_profile"

    def test_public_profile_accessible(self, client):
        """Public profile works without auth."""
        _signup(client, "smoke_public")
        res = client.get("/profile/smoke_public")
        assert res.status_code == 200

    def test_algo_feed_accessible(self, client):
        """Algo feed responds."""
        res = client.get("/posts/algo")
        assert res.status_code == 200
        assert "posts" in res.json()

    def test_search_accessible(self, client):
        """Search endpoints respond."""
        res = client.get("/posts/search/posts?q=test")
        assert res.status_code == 200
        res = client.get("/posts/search/users?q=test")
        assert res.status_code == 200

    def test_single_post_accessible(self, client):
        """Single post endpoint works."""
        _signup(client, "smoke_single")
        h = _login(client, "smoke_single")
        client.post(
            "/posts/add",
            data={"text": "Single smoke", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        res = client.get(f"/posts/{pid}")
        assert res.status_code == 200
        assert res.json()["post"]["text"] == "Single smoke"

    def test_replies_accessible(self, client):
        """Replies endpoint works."""
        res = client.get("/posts/999/replies")
        assert res.status_code == 200

    def test_verify_endpoint_accessible(self, client):
        """Verify endpoint responds (with invalid token)."""
        res = client.get("/auth/verify?token=invalid")
        assert res.status_code == 400
