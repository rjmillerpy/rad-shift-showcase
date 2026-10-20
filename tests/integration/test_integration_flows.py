"""
Integration tests (part 1) — user, post, social, and draft lifecycle flows.
"""

from tests.integration._helpers import _create_post, _login, _signup


class TestUserLifecycle:
    """Signup -> login -> view profile -> update bio -> verify profile."""

    def test_full_user_lifecycle(self, client):
        # Signup
        res = _signup(client, "lifecycle_user", "securepass1")
        assert res.status_code == 200
        assert "User created successfully" in res.json()["message"]

        # Login
        res = client.post(
            "/auth/login", json={"username": "lifecycle_user", "password": "securepass1"}
        )
        assert res.status_code == 200
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # View profile (no bio yet)
        res = client.get("/profile/me", headers=headers)
        assert res.status_code == 200
        profile = res.json()
        assert profile["username"] == "lifecycle_user"
        assert profile["bio"] is None
        assert profile["posts"] == []

        # Update bio
        res = client.put("/profile/me", json={"bio": "Hello world!"}, headers=headers)
        assert res.status_code == 200

        # Verify bio persisted
        res = client.get("/profile/me", headers=headers)
        assert res.json()["bio"] == "Hello world!"

        # Public profile also shows updated bio
        res = client.get("/profile/lifecycle_user")
        assert res.status_code == 200
        assert res.json()["bio"] == "Hello world!"

    def test_duplicate_signup_then_login_original(self, client):
        _signup(client, "dup_user", "password123")
        res = _signup(client, "dup_user", "otherpass123")
        assert res.status_code == 400
        assert "already exists" in res.json()["detail"]

        # Original password still works
        res = client.post("/auth/login", json={"username": "dup_user", "password": "password123"})
        assert res.status_code == 200
        assert "access_token" in res.json()


class TestPostLifecycle:
    """Create post -> like -> repost -> share -> save -> verify saved -> unsave -> verify."""

    def test_full_post_lifecycle(self, client):
        _signup(client, "poster")
        headers = _login(client, "poster")

        # Create post
        res = _create_post(client, headers, text="My first post")
        assert res.status_code == 200
        assert res.json()["message"] == "Post created"

        # Get posts and find ours
        res = client.get("/posts/", headers=headers)
        posts = res.json()["posts"]
        post = next(p for p in posts if p["text"] == "My first post")
        pid = post["id"]
        assert post["likes"] == 0
        assert post["is_me"] is True

        # Like
        res = client.post(f"/posts/like/{pid}", headers=headers)
        assert res.json() == {"likes": 1, "action": "liked"}

        # Verify like reflected in feed
        res = client.get("/posts/", headers=headers)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["likes"] == 1
        assert post["liked_by_me"] is True

        # Repost
        res = client.post(f"/posts/repost/{pid}", headers=headers)
        assert res.json()["action"] == "re-posted"
        assert res.json()["reposts"] == 1

        # Share
        res = client.post(f"/posts/share/{pid}", headers=headers)
        assert res.json()["shares"] == 1
        assert "/post/" in res.json()["share_url"]

        # Save
        res = client.post(f"/posts/save/{pid}", headers=headers)
        assert res.json() == {"saves": 1, "action": "saved"}

        # Verify in saved list
        res = client.get("/posts/saved", headers=headers)
        saved = res.json()["posts"]
        assert len(saved) == 1
        assert saved[0]["id"] == pid
        assert saved[0]["is_saved_by_me"] is True

        # Unsave
        res = client.post(f"/posts/save/{pid}", headers=headers)
        assert res.json() == {"saves": 0, "action": "unsaved"}

        # Verify removed from saved list
        res = client.get("/posts/saved", headers=headers)
        assert len(res.json()["posts"]) == 0

        # Unlike
        res = client.post(f"/posts/like/{pid}", headers=headers)
        assert res.json() == {"likes": 0, "action": "unliked"}

        # Un-repost
        res = client.post(f"/posts/repost/{pid}", headers=headers)
        assert res.json()["action"] == "un-re-posted"

        # Verify all counters reset
        res = client.get("/posts/", headers=headers)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["likes"] == 0
        assert post["reposts"] == 0
        assert post["liked_by_me"] is False
        assert post["reposted_by_me"] is False


class TestSocialInteractions:
    """User A creates post -> User B follows A -> B sees post in following feed ->
    B likes A's post -> A sees like -> B unfollows -> following feed empty."""

    def test_follow_and_feed_interaction(self, client):
        # Setup two users
        _signup(client, "author", "password123")
        _signup(client, "reader", "password123")
        author_h = _login(client, "author")
        reader_h = _login(client, "reader")

        # Author creates a post
        _create_post(client, author_h, text="Author's post")

        # Reader's following feed is empty (not following anyone)
        res = client.get("/posts/following", headers=reader_h)
        assert len(res.json()["posts"]) == 0

        # Reader follows author
        res = client.post("/follow/author", headers=reader_h)
        assert res.status_code == 200

        # Reader now sees author's post in following feed
        res = client.get("/posts/following", headers=reader_h)
        posts = res.json()["posts"]
        assert len(posts) == 1
        assert posts[0]["text"] == "Author's post"
        assert posts[0]["is_followed_by_me"] is True
        assert posts[0]["is_me"] is False

        # Reader likes author's post
        pid = posts[0]["id"]
        res = client.post(f"/posts/like/{pid}", headers=reader_h)
        assert res.json()["action"] == "liked"

        # Author sees the like count increased
        res = client.get("/posts/", headers=author_h)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["likes"] == 1
        assert post["liked_by_me"] is False  # Author didn't like it

        # Reader unfollows author
        res = client.post("/follow/un/author", headers=reader_h)
        assert res.status_code == 200

        # Following feed is empty again
        res = client.get("/posts/following", headers=reader_h)
        assert len(res.json()["posts"]) == 0

    def test_mutual_follow(self, client):
        _signup(client, "user_a", "password123")
        _signup(client, "user_b", "password123")
        a_h = _login(client, "user_a")
        b_h = _login(client, "user_b")

        _create_post(client, a_h, text="A's post")
        _create_post(client, b_h, text="B's post")

        # Both follow each other
        client.post("/follow/user_b", headers=a_h)
        client.post("/follow/user_a", headers=b_h)

        # A sees B's post in following feed
        res = client.get("/posts/following", headers=a_h)
        texts = {p["text"] for p in res.json()["posts"]}
        assert "B's post" in texts

        # B sees A's post in following feed
        res = client.get("/posts/following", headers=b_h)
        texts = {p["text"] for p in res.json()["posts"]}
        assert "A's post" in texts

    def test_repost_appears_in_follower_feed(self, client):
        _signup(client, "original_author", "password123")
        _signup(client, "reposter", "password123")
        _signup(client, "follower", "password123")

        oa_h = _login(client, "original_author")
        rp_h = _login(client, "reposter")
        fl_h = _login(client, "follower")

        # Original author creates post
        _create_post(client, oa_h, text="Original content")
        res = client.get("/posts/", headers=oa_h)
        pid = next(p["id"] for p in res.json()["posts"] if p["text"] == "Original content")

        # Follower follows reposter (not original author)
        client.post("/follow/reposter", headers=fl_h)

        # Reposter reposts the original post
        client.post(f"/posts/repost/{pid}", headers=rp_h)

        # Follower sees the reposted post in following feed
        res = client.get("/posts/following", headers=fl_h)
        posts = res.json()["posts"]
        reposted = next((p for p in posts if p["id"] == pid), None)
        assert reposted is not None
        assert "reposter" in (reposted.get("reposted_by") or [])


class TestDraftLifecycle:
    """Create draft -> verify hidden from feed -> verify in drafts list ->
    publish -> verify now in feed -> verify removed from drafts."""

    def test_full_draft_lifecycle(self, client):
        _signup(client, "drafter")
        headers = _login(client, "drafter")

        # Create draft
        res = _create_post(client, headers, text="Draft post", is_draft=True)
        assert res.json()["message"] == "Draft saved"

        # Draft NOT in public feed
        res = client.get("/posts/", headers=headers)
        texts = [p["text"] for p in res.json()["posts"]]
        assert "Draft post" not in texts

        # Draft IS in drafts list
        res = client.get("/posts/drafts", headers=headers)
        drafts = res.json()["drafts"]
        assert len(drafts) == 1
        assert drafts[0]["text"] == "Draft post"
        draft_id = drafts[0]["id"]

        # Publish the draft
        res = client.post(f"/posts/drafts/publish/{draft_id}", headers=headers)
        assert res.json()["status"] == "published"

        # Now appears in public feed
        res = client.get("/posts/", headers=headers)
        texts = [p["text"] for p in res.json()["posts"]]
        assert "Draft post" in texts

        # Drafts list is empty
        res = client.get("/posts/drafts", headers=headers)
        assert len(res.json()["drafts"]) == 0

    def test_cannot_publish_already_published(self, client):
        _signup(client, "drafter2")
        headers = _login(client, "drafter2")

        _create_post(client, headers, text="Normal post")
        res = client.get("/posts/", headers=headers)
        pid = res.json()["posts"][0]["id"]

        res = client.post(f"/posts/drafts/publish/{pid}", headers=headers)
        assert res.status_code == 400
        assert "already published" in res.json()["detail"]
