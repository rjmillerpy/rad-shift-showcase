"""API contract tests for feed endpoints (pagination, algo, tags, multi-image)."""

import json

from tests.helpers import login, make_post, setup_user, signup


class TestPaginationAPI:
    """Pagination on all feed endpoints."""

    def _seed_posts(self, client, username, count):
        h = setup_user(client, username)
        for i in range(count):
            make_post(client, h, text=f"Post {i} by {username}")
        return h

    def test_default_limit_is_20(self, client):
        h = self._seed_posts(client, "pag_default", 25)
        res = client.get("/posts/", headers=h)
        assert len(res.json()["posts"]) == 20
        assert res.json()["has_more"] is True

    def test_custom_limit(self, client):
        h = self._seed_posts(client, "pag_limit", 10)
        res = client.get("/posts/?limit=5", headers=h)
        assert len(res.json()["posts"]) == 5
        assert res.json()["has_more"] is True

    def test_offset_skips_posts(self, client):
        h = self._seed_posts(client, "pag_offset", 10)
        page1 = client.get("/posts/?offset=0&limit=5", headers=h).json()
        page2 = client.get("/posts/?offset=5&limit=5", headers=h).json()
        ids1 = {p["id"] for p in page1["posts"]}
        ids2 = {p["id"] for p in page2["posts"]}
        assert ids1.isdisjoint(ids2)  # No overlap

    def test_has_more_false_at_end(self, client):
        h = self._seed_posts(client, "pag_end", 3)
        res = client.get("/posts/?limit=10", headers=h)
        assert res.json()["has_more"] is False

    def test_pagination_on_following_feed(self, client):
        self._seed_posts(client, "pag_author", 10)
        follower_h = setup_user(client, "pag_follower")
        client.post("/follow/pag_author", headers=follower_h)
        res = client.get("/posts/following?limit=5", headers=follower_h)
        assert len(res.json()["posts"]) == 5
        assert res.json()["has_more"] is True

    def test_pagination_on_algo_feed(self, client):
        self._seed_posts(client, "pag_algo", 10)
        res = client.get("/posts/algo?limit=5")
        assert len(res.json()["posts"]) == 5
        assert res.json()["has_more"] is True

    def test_response_includes_has_more_key(self, client):
        res = client.get("/posts/")
        assert "has_more" in res.json()


class TestAlgoFeedAPI:
    """GET /posts/algo — algorithmic feed."""

    def test_algo_response_schema(self, client):
        h = setup_user(client, "algo_schema")
        make_post(client, h)
        res = client.get("/posts/algo")
        assert res.status_code == 200
        body = res.json()
        assert "posts" in body
        assert "has_more" in body
        assert isinstance(body["posts"], list)

    def test_algo_orders_by_engagement(self, client):
        h = setup_user(client, "algo_engage")
        # Create two posts
        make_post(client, h, text="Low engagement")
        make_post(client, h, text="High engagement")
        posts = client.get("/posts/?limit=100", headers=h).json()["posts"]
        high_id = next(p["id"] for p in posts if p["text"] == "High engagement")
        # Like the high engagement post multiple times via different users
        for i in range(3):
            u = f"algo_liker_{i}"
            signup(client, u)
            uh = login(client, u)
            client.post(f"/posts/like/{high_id}", headers=uh)

        res = client.get("/posts/algo?limit=10", headers=h)
        algo_posts = res.json()["posts"]
        # High engagement post should come before low engagement
        high_idx = next(i for i, p in enumerate(algo_posts) if p["id"] == high_id)
        low_idx = next(i for i, p in enumerate(algo_posts) if p["text"] == "Low engagement")
        assert high_idx < low_idx

    def test_algo_allows_anonymous(self, client):
        h = setup_user(client, "algo_anon")
        make_post(client, h)
        res = client.get("/posts/algo")
        assert res.status_code == 200

    def test_algo_authenticated_shows_flags(self, client):
        h = setup_user(client, "algo_auth")
        make_post(client, h)
        pid = client.get("/posts/algo", headers=h).json()["posts"][0]["id"]
        client.post(f"/posts/like/{pid}", headers=h)
        res = client.get("/posts/algo", headers=h)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["liked_by_me"] is True

    def test_algo_excludes_drafts(self, client):
        h = setup_user(client, "algo_draft")
        make_post(client, h, text="Visible", is_draft="false")
        make_post(client, h, text="Draft", is_draft="true")
        res = client.get("/posts/algo", headers=h)
        texts = [p["text"] for p in res.json()["posts"]]
        assert "Visible" in texts
        assert "Draft" not in texts


# ═══════════════════════════════════════════════════════════════════════════════


class TestTagsAPI:
    """GET /posts/tags — extract tags from feed posts."""

    def test_tags_response_schema(self, client):
        h = setup_user(client, "tags_schema")
        make_post(client, h, text="Tagged", post_metadata=json.dumps({"tags": "python|rust"}))

        res = client.get("/posts/tags")
        assert res.status_code == 200
        body = res.json()
        assert "tags" in body
        assert isinstance(body["tags"], list)

    def test_tags_extracts_from_metadata(self, client):
        h = setup_user(client, "tags_extract")
        make_post(client, h, text="Post 1", post_metadata=json.dumps({"tags": "alpha|beta"}))
        make_post(client, h, text="Post 2", post_metadata=json.dumps({"tags": "gamma"}))

        res = client.get("/posts/tags?limit=10")
        tags = res.json()["tags"]
        assert "alpha" in tags
        assert "beta" in tags
        assert "gamma" in tags

    def test_tags_respects_feed_param(self, client):
        h = setup_user(client, "tags_feed")
        make_post(client, h, text="Algo post", post_metadata=json.dumps({"tags": "algotag"}))

        res = client.get("/posts/tags?feed=algo")
        assert res.status_code == 200
        assert isinstance(res.json()["tags"], list)

    def test_tags_respects_limit(self, client):
        h = setup_user(client, "tags_limit")
        for i in range(5):
            make_post(client, h, text=f"Tagged {i}", post_metadata=json.dumps({"tags": f"tag{i}"}))

        res = client.get("/posts/tags?limit=3")
        assert len(res.json()["tags"]) <= 3

    def test_tags_deduplicates(self, client):
        h = setup_user(client, "tags_dedup")
        make_post(client, h, text="Post A", post_metadata=json.dumps({"tags": "same"}))
        make_post(client, h, text="Post B", post_metadata=json.dumps({"tags": "same"}))

        res = client.get("/posts/tags?limit=10")
        tags = res.json()["tags"]
        assert tags.count("same") == 1

    def test_tags_handles_empty_metadata(self, client):
        h = setup_user(client, "tags_empty")
        make_post(client, h, text="No tags")

        res = client.get("/posts/tags")
        assert res.status_code == 200

    def test_tags_anonymous_access(self, client):
        res = client.get("/posts/tags")
        assert res.status_code == 200


class TestMultiImageAPI:
    """API tests for multi-image post support."""

    def test_post_response_includes_image_urls(self, client):
        headers = setup_user(client, "multi_img_schema")
        make_post(client, headers, text="Multi image schema test")
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]
        res = client.get(f"/posts/{pid}")
        post = res.json()["post"]
        assert "image_urls" in post
        # Empty by default (no images uploaded)
        assert (
            post["image_urls"] == []
            or post["image_urls"] is None
            or isinstance(post["image_urls"], list)
        )

    def test_feed_posts_include_image_urls_field(self, client):
        headers = setup_user(client, "multi_img_feed")
        make_post(client, headers, text="Feed image urls test")
        res = client.get("/posts/", headers=headers)
        post = res.json()["posts"][0]
        assert "image_urls" in post

    def test_add_post_accepts_images_param(self, client):
        """The /posts/add endpoint should accept 'images' as a list of files."""
        headers = setup_user(client, "multi_img_add")
        import io

        img1 = io.BytesIO(b"fake image 1")
        img2 = io.BytesIO(b"fake image 2")
        res = client.post(
            "/posts/add",
            data={"text": "Multi image post", "post_metadata": "{}", "is_draft": "false"},
            files=[
                ("images", ("pic1.jpg", img1, "image/jpeg")),
                ("images", ("pic2.jpg", img2, "image/jpeg")),
            ],
            headers=headers,
        )
        assert res.status_code == 200
        body = res.json()
        assert "image_urls" in body
        assert isinstance(body["image_urls"], list)
        assert len(body["image_urls"]) == 2

    def test_single_image_still_works(self, client):
        """Backward compat: single 'image' param still sets image_url."""
        headers = setup_user(client, "single_img_compat")
        import io

        img = io.BytesIO(b"fake image")
        res = client.post(
            "/posts/add",
            data={"text": "Single image post", "post_metadata": "{}", "is_draft": "false"},
            files=[("image", ("pic.jpg", img, "image/jpeg"))],
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["image_url"] is not None
