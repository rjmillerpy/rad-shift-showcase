"""
Integration tests (part 2) — reply/quote chains, slop filtering,
anonymous access, rapid toggles, metadata, and profile-pic flow.
"""

import io
import json

from tests.integration._helpers import _create_post, _login, _signup


class TestReplyAndQuoteChains:
    """Create post -> reply -> reply to reply -> quote -> check counts."""

    def test_nested_replies_and_counts(self, client):
        _signup(client, "op_user")
        headers = _login(client, "op_user")

        # Original post
        _create_post(client, headers, text="Original")
        res = client.get("/posts/", headers=headers)
        op_id = res.json()["posts"][0]["id"]

        # Reply 1
        data = {
            "text": "Reply 1",
            "post_metadata": "{}",
            "is_draft": "false",
            "is_reply": "true",
            "parent_post_id": str(op_id),
        }
        client.post("/posts/add", data=data, headers=headers)

        # Reply 2
        data["text"] = "Reply 2"
        client.post("/posts/add", data=data, headers=headers)

        # Check replies endpoint
        res = client.get(f"/posts/{op_id}/replies", headers=headers)
        replies = res.json()["replies"]
        assert len(replies) == 2

        # Check replies_count on original post
        res = client.get("/posts/", headers=headers)
        op = next(p for p in res.json()["posts"] if p["id"] == op_id)
        assert op["replies_count"] == 2

        # Reply to reply 1
        r1_id = replies[0]["id"]
        data = {
            "text": "Nested reply",
            "post_metadata": "{}",
            "is_draft": "false",
            "is_reply": "true",
            "parent_post_id": str(r1_id),
        }
        client.post("/posts/add", data=data, headers=headers)

        # Check nested replies
        res = client.get(f"/posts/{r1_id}/replies", headers=headers)
        assert len(res.json()["replies"]) == 1

    def test_quote_post_and_count(self, client):
        _signup(client, "quoter")
        headers = _login(client, "quoter")

        # Original
        _create_post(client, headers, text="Quotable content")
        res = client.get("/posts/", headers=headers)
        orig_id = res.json()["posts"][0]["id"]

        # Quote it
        data = {
            "text": "My commentary",
            "post_metadata": "{}",
            "is_draft": "false",
            "parent_post_id": str(orig_id),
        }
        client.post("/posts/add", data=data, headers=headers)

        # Verify quote shows the quoted_post data
        res = client.get("/posts/", headers=headers)
        quote_post = next(p for p in res.json()["posts"] if p["text"] == "My commentary")
        assert quote_post["quoted_post"] is not None
        assert quote_post["quoted_post"]["text"] == "Quotable content"

        # Verify quotes_count on original
        orig = next(p for p in res.json()["posts"] if p["id"] == orig_id)
        assert orig["quotes_count"] == 1


class TestSlopFiltering:
    """User marks post as slop -> post disappears from their feed ->
    other user still sees it."""

    def test_slop_filtering_across_users(self, client):
        _signup(client, "poster_s", "password123")
        _signup(client, "reader_s", "password123")
        poster_h = _login(client, "poster_s")
        reader_h = _login(client, "reader_s")

        # Poster creates a post
        _create_post(client, poster_h, text="Controversial take")
        res = client.get("/posts/", headers=poster_h)
        pid = next(p["id"] for p in res.json()["posts"] if p["text"] == "Controversial take")

        # Both see it initially
        res = client.get("/posts/", headers=reader_h)
        assert any(p["id"] == pid for p in res.json()["posts"])

        # Reader marks it as slop
        res = client.post(
            f"/posts/slop/{pid}", json={"reason": "Engagement Bait"}, headers=reader_h
        )
        assert res.json()["status"] == "ok"

        # Verify slop_count increased
        res = client.get("/posts/", headers=poster_h)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["slop_count"] == 1

        # Reader no longer sees it
        res = client.get("/posts/", headers=reader_h)
        assert not any(p["id"] == pid for p in res.json()["posts"])

        # Poster still sees it
        res = client.get("/posts/", headers=poster_h)
        assert any(p["id"] == pid for p in res.json()["posts"])

    def test_slop_reason_update(self, client):
        _signup(client, "slop_updater", "password123")
        headers = _login(client, "slop_updater")

        _create_post(client, headers, text="Sloppy")
        res = client.get("/posts/", headers=headers)
        pid = res.json()["posts"][0]["id"]

        # Mark as slop
        client.post(f"/posts/slop/{pid}", json={"reason": "AI"}, headers=headers)

        # Update reason
        res = client.post(f"/posts/slop/{pid}", json={"reason": "Fake"}, headers=headers)
        assert res.json()["status"] == "updated"


class TestAnonVsAuth:
    """Verify anonymous access works for public endpoints and fails for protected ones."""

    def test_anonymous_can_view_posts(self, client):
        _signup(client, "public_poster")
        h = _login(client, "public_poster")
        _create_post(client, h, text="Public post")

        # Anonymous user can see posts
        res = client.get("/posts/")
        assert res.status_code == 200
        posts = res.json()["posts"]
        assert len(posts) >= 1
        # Anonymous user sees default interaction flags
        p = posts[0]
        assert p["liked_by_me"] is False
        assert p["is_me"] is False

    def test_anonymous_can_share(self, client):
        _signup(client, "share_poster")
        h = _login(client, "share_poster")
        _create_post(client, h, text="Share me")
        res = client.get("/posts/")
        pid = res.json()["posts"][0]["id"]

        # Anonymous share increments counter
        res = client.post(f"/posts/share/{pid}")
        assert res.status_code == 200
        assert res.json()["shares"] == 1

    def test_anonymous_cannot_like(self, client):
        _signup(client, "liker_poster")
        h = _login(client, "liker_poster")
        _create_post(client, h, text="Like me")
        res = client.get("/posts/")
        pid = res.json()["posts"][0]["id"]

        res = client.post(f"/posts/like/{pid}")
        assert res.status_code == 401

    def test_anonymous_cannot_create_post(self, client):
        res = client.post("/posts/add", data={"text": "Anon post", "post_metadata": "{}"})
        assert res.status_code == 401

    def test_anonymous_cannot_follow(self, client):
        _signup(client, "target_user")
        res = client.post("/follow/target_user")
        assert res.status_code == 401

    def test_anonymous_can_view_public_profile(self, client):
        _signup(client, "public_profile")
        h = _login(client, "public_profile")
        client.put("/profile/me", json={"bio": "I am public"}, headers=h)

        res = client.get("/profile/public_profile")
        assert res.status_code == 200
        assert res.json()["bio"] == "I am public"

    def test_anonymous_cannot_view_own_profile(self, client):
        res = client.get("/profile/me")
        assert res.status_code == 401


class TestRapidToggles:
    """Rapid like/unlike cycles to verify counter consistency with atomic updates."""

    def test_rapid_like_toggles(self, client):
        _signup(client, "rapid_user")
        headers = _login(client, "rapid_user")
        _create_post(client, headers, text="Toggle me")

        res = client.get("/posts/", headers=headers)
        pid = res.json()["posts"][0]["id"]

        # Like/unlike 5 times rapidly
        for i in range(5):
            res = client.post(f"/posts/like/{pid}", headers=headers)
            expected_action = "liked" if i % 2 == 0 else "unliked"
            assert res.json()["action"] == expected_action

        # After 5 toggles (odd number), should be liked with count 1
        res = client.get("/posts/", headers=headers)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["likes"] == 1
        assert post["liked_by_me"] is True

    def test_rapid_save_toggles(self, client):
        _signup(client, "rapid_saver")
        headers = _login(client, "rapid_saver")
        _create_post(client, headers, text="Save me repeatedly")

        res = client.get("/posts/", headers=headers)
        pid = res.json()["posts"][0]["id"]

        for _ in range(4):
            client.post(f"/posts/save/{pid}", headers=headers)

        # After 4 toggles (even), should be unsaved with count 0
        res = client.get("/posts/saved", headers=headers)
        assert len(res.json()["posts"]) == 0


class TestMetadataAndMedia:
    """Create posts with metadata and verify it round-trips through the API."""

    def test_metadata_round_trip(self, client):
        _signup(client, "meta_user")
        headers = _login(client, "meta_user")

        metadata = json.dumps(
            {"tags": "python|fastapi", "tagged_users": ["meta_user"], "location": "NYC"}
        )
        data = {"text": "Tagged post", "post_metadata": metadata, "is_draft": "false"}
        res = client.post("/posts/add", data=data, headers=headers)
        assert res.status_code == 200

        # Verify metadata parsed correctly in feed
        res = client.get("/posts/", headers=headers)
        post = next(p for p in res.json()["posts"] if p["text"] == "Tagged post")
        assert post["post_metadata"]["tags"] == ["python", "fastapi"]
        assert post["post_metadata"]["tagged_users"] == ["meta_user"]
        assert post["post_metadata"]["location"] == "NYC"

    def test_post_with_image_upload(self, client):
        _signup(client, "uploader")
        headers = _login(client, "uploader")

        image = io.BytesIO(b"fake image data")
        res = client.post(
            "/posts/add",
            data={
                "text": "Photo post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"image": ("photo.jpg", image, "image/jpeg")},
            headers=headers,
        )

        assert res.status_code == 200
        assert res.json()["image_url"] is not None
        assert "photo.jpg" not in res.json()["image_url"]  # S3 key uses username_timestamp

    def test_post_text_length_validation(self, client):
        _signup(client, "longpost")
        headers = _login(client, "longpost")

        long_text = "x" * 5001
        res = client.post(
            "/posts/add",
            data={
                "text": long_text,
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=headers,
        )
        assert res.status_code == 400
        assert "5000" in res.json()["detail"]


class TestProfilePictureFlow:
    """Upload profile pic -> verify URL in profile -> verify in posts."""

    def test_profile_pic_persists_to_posts(self, client):
        _signup(client, "pic_user")
        headers = _login(client, "pic_user")

        pic = io.BytesIO(b"fake pic data")
        res = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("avatar.jpg", pic, "image/jpeg")},
            headers=headers,
        )
        assert res.status_code == 200
        pic_url = res.json()["url"]

        # Profile shows the URL
        res = client.get("/profile/me", headers=headers)
        assert res.json()["profile_picture_url"] == pic_url

        # Create a post and verify profile pic in feed
        _create_post(client, headers, text="Post with pic")
        res = client.get("/posts/", headers=headers)
        post = next(p for p in res.json()["posts"] if p["text"] == "Post with pic")
        assert post["profile_picture_url"] == pic_url
