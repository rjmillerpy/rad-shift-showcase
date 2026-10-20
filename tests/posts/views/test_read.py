"""API contract tests for /posts read endpoints."""

from tests.helpers import make_post, setup_user


class TestPostsReadAPI:
    """Read endpoints: GET /posts/, GET /posts/{id}, GET /posts/{id}/replies,
    GET /posts/saved, GET /posts/drafts, GET /posts/following."""

    # ── GET /posts/ ──────────────────────────────────────────────────────

    def test_get_posts_response_schema(self, client):
        headers = setup_user(client, "post_schema")
        make_post(client, headers)

        res = client.get("/posts/")
        assert res.status_code == 200
        body = res.json()
        assert "posts" in body
        assert isinstance(body["posts"], list)

        post = body["posts"][0]
        required_keys = {
            "id",
            "text",
            "likes",
            "shares",
            "reposts",
            "saves",
            "laughs",
            "liked_by_me",
            "unix_timestamp",
            "post_metadata",
            "username",
            "profile_picture_url",
            "image_url",
            "video_url",
            "audio_url",
            "replies_count",
            "quotes_count",
            "slop_count",
        }
        assert required_keys.issubset(post.keys())
        assert isinstance(post["id"], int)
        assert isinstance(post["text"], str)
        assert isinstance(post["likes"], int)
        assert isinstance(post["laughs"], int)
        assert isinstance(post["liked_by_me"], bool)
        assert isinstance(post["unix_timestamp"], int)
        assert isinstance(post["post_metadata"], dict)
        assert isinstance(post["replies_count"], int)
        assert isinstance(post["quotes_count"], int)
        assert isinstance(post["slop_count"], int)

    def test_get_posts_anonymous_returns_200(self, client):
        res = client.get("/posts/")
        assert res.status_code == 200
        assert "posts" in res.json()

    def test_get_posts_authenticated_shows_interaction_flags(self, client):
        headers = setup_user(client, "flag_user")
        make_post(client, headers)

        res = client.get("/posts/", headers=headers)
        post = res.json()["posts"][0]
        assert "is_me" in post
        assert post["is_me"] is True
        assert "is_followed_by_me" in post
        assert "is_saved_by_me" in post

    # ── GET /posts/{id} ──────────────────────────────────────────────────

    def test_get_single_post_response_schema(self, client):
        headers = setup_user(client, "single_post_api")
        make_post(client, headers, text="Single post test")
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.get(f"/posts/{pid}")
        assert res.status_code == 200
        body = res.json()
        assert "post" in body
        post = body["post"]
        required_keys = {
            "id",
            "text",
            "likes",
            "shares",
            "reposts",
            "saves",
            "laughs",
            "liked_by_me",
            "unix_timestamp",
            "post_metadata",
            "username",
            "replies_count",
            "quotes_count",
            "slop_count",
        }
        assert required_keys.issubset(post.keys())
        assert post["text"] == "Single post test"
        assert post["username"] == "single_post_api"

    def test_get_single_post_authenticated(self, client):
        h_a = setup_user(client, "single_auth_a")
        make_post(client, h_a, text="Auth post")
        pid = client.get("/posts/", headers=h_a).json()["posts"][0]["id"]

        h_b = setup_user(client, "single_auth_b")
        client.post(f"/posts/like/{pid}", headers=h_b)

        res = client.get(f"/posts/{pid}", headers=h_b)
        post = res.json()["post"]
        assert post["liked_by_me"] is True
        assert post["is_me"] is False

    def test_get_single_post_not_found(self, client):
        res = client.get("/posts/99999")
        assert res.status_code == 404
        assert "detail" in res.json()

    def test_get_single_post_anonymous(self, client):
        h = setup_user(client, "single_anon")
        make_post(client, h, text="Anon view")
        pid = client.get("/posts/").json()["posts"][0]["id"]

        res = client.get(f"/posts/{pid}")
        assert res.status_code == 200
        assert res.json()["post"]["liked_by_me"] is False

    # ── GET /posts/saved ─────────────────────────────────────────────────

    def test_saved_response_schema(self, client):
        headers = setup_user(client, "saved_api")
        res = client.get("/posts/saved", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "posts" in body
        assert isinstance(body["posts"], list)

    def test_saved_requires_auth(self, client):
        res = client.get("/posts/saved")
        assert res.status_code == 401

    # ── GET /posts/drafts ────────────────────────────────────────────────

    def test_drafts_response_schema(self, client):
        headers = setup_user(client, "drafts_api")
        res = client.get("/posts/drafts", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "drafts" in body
        assert isinstance(body["drafts"], list)

    def test_drafts_requires_auth(self, client):
        res = client.get("/posts/drafts")
        assert res.status_code == 401

    # ── GET /posts/following ─────────────────────────────────────────────

    def test_following_response_schema(self, client):
        headers = setup_user(client, "following_api")
        res = client.get("/posts/following", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "posts" in body
        assert isinstance(body["posts"], list)

    def test_following_requires_auth(self, client):
        res = client.get("/posts/following")
        assert res.status_code == 401

    # ── GET /posts/{id}/replies ──────────────────────────────────────────

    def test_replies_response_schema(self, client):
        headers = setup_user(client, "replies_api")
        make_post(client, headers, text="Parent")
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        # Add a reply
        client.post(
            "/posts/add",
            data={
                "text": "A reply",
                "post_metadata": "{}",
                "is_draft": "false",
                "is_reply": "true",
                "parent_post_id": str(pid),
            },
            headers=headers,
        )

        res = client.get(f"/posts/{pid}/replies")
        assert res.status_code == 200
        body = res.json()
        assert "replies" in body
        assert isinstance(body["replies"], list)
        assert len(body["replies"]) == 1
        assert body["replies"][0]["text"] == "A reply"

    def test_replies_anonymous_allowed(self, client):
        res = client.get("/posts/999/replies")
        assert res.status_code == 200
        assert res.json()["replies"] == []
