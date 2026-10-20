"""API contract tests for /profile and /follow endpoints."""

import io

from tests.helpers import login, make_post, setup_user


class TestProfileAPI:
    """GET/PUT /profile/me, POST /profile/me/upload-profile-pic, GET /profile/{username}"""

    # ── GET /profile/me ──────────────────────────────────────────────────

    def test_profile_me_response_schema(self, client):
        headers = setup_user(client, "profile_api")
        res = client.get("/profile/me", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "username" in body
        assert "bio" in body
        assert "profile_picture_url" in body
        assert "posts" in body
        assert body["username"] == "profile_api"
        assert isinstance(body["posts"], list)

    def test_profile_me_requires_auth(self, client):
        res = client.get("/profile/me")
        assert res.status_code == 401

    # ── PUT /profile/me ──────────────────────────────────────────────────

    def test_update_profile_response_schema(self, client):
        headers = setup_user(client, "update_api")
        res = client.put("/profile/me", json={"bio": "New bio"}, headers=headers)
        assert res.status_code == 200
        assert res.json()["message"] == "Profile updated"

    def test_update_profile_requires_auth(self, client):
        res = client.put("/profile/me", json={"bio": "No auth"})
        assert res.status_code == 401

    def test_update_profile_empty_body(self, client):
        headers = setup_user(client, "empty_update")
        res = client.put("/profile/me", json={}, headers=headers)
        assert res.status_code == 200  # No fields to update, still succeeds

    # ── POST /profile/me/upload-profile-pic ──────────────────────────────

    def test_upload_pic_response_schema(self, client):
        headers = setup_user(client, "pic_api")
        pic = io.BytesIO(b"fake pic")
        res = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("avatar.jpg", pic, "image/jpeg")},
            headers=headers,
        )
        assert res.status_code == 200
        body = res.json()
        assert "message" in body
        assert "url" in body
        assert body["url"].startswith("https://")

    def test_upload_pic_empty_filename(self, client):
        headers = setup_user(client, "empty_pic")
        pic = io.BytesIO(b"fake pic")
        res = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("", pic, "image/jpeg")},
            headers=headers,
        )
        assert res.status_code in (400, 422)  # FastAPI may validate before handler

    def test_upload_pic_requires_auth(self, client):
        pic = io.BytesIO(b"fake pic")
        res = client.post(
            "/profile/me/upload-profile-pic", files={"file": ("avatar.jpg", pic, "image/jpeg")}
        )
        assert res.status_code == 401

    # ── GET /profile/{username} ──────────────────────────────────────────

    def test_public_profile_response_schema(self, client):
        headers = setup_user(client, "public_api")
        client.put("/profile/me", json={"bio": "Public bio"}, headers=headers)
        make_post(client, headers, text="Public post")

        res = client.get("/profile/public_api")
        assert res.status_code == 200
        body = res.json()
        assert body["username"] == "public_api"
        assert body["bio"] == "Public bio"
        assert len(body["posts"]) == 1
        assert body["posts"][0]["text"] == "Public post"

    def test_public_profile_not_found(self, client):
        res = client.get("/profile/nonexistent_user")
        assert res.status_code == 404

    def test_public_profile_no_auth_required(self, client):
        setup_user(client, "no_auth_profile")
        res = client.get("/profile/no_auth_profile")
        assert res.status_code == 200

    def test_public_profile_with_auth_includes_interaction_status(self, client):
        """When viewing another user's profile while authenticated, liked_by_me etc. should be populated."""
        viewer_h = setup_user(client, "profile_viewer")
        setup_user(client, "profile_target")
        make_post(client, login(client, "profile_target"), text="Target post")

        res = client.get("/profile/profile_target", headers=viewer_h)
        assert res.status_code == 200
        post = res.json()["posts"][0]
        assert "liked_by_me" in post
        assert post["liked_by_me"] is False

    def test_upload_pic_bad_extension_rejected(self, client):
        import io

        headers = setup_user(client, "bad_ext_pic")
        pic = io.BytesIO(b"fake data")
        res = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("hack.exe", pic, "application/octet-stream")},
            headers=headers,
        )
        assert res.status_code == 500
        assert "not allowed" in res.json()["detail"].lower()


class TestFollowAPI:
    """POST /follow/{username}, POST /follow/un/{username}"""

    def test_follow_response_schema(self, client):
        setup_user(client, "follow_target")
        headers = setup_user(client, "follow_api")

        res = client.post("/follow/follow_target", headers=headers)
        assert res.status_code == 200
        assert "message" in res.json()
        assert "following" in res.json()["message"]

    def test_follow_self_returns_400(self, client):
        headers = setup_user(client, "self_follow")
        res = client.post("/follow/self_follow", headers=headers)
        assert res.status_code == 400
        assert "yourself" in res.json()["detail"].lower()

    def test_follow_nonexistent_returns_404(self, client):
        headers = setup_user(client, "follow_ghost")
        res = client.post("/follow/nonexistent_user", headers=headers)
        assert res.status_code == 404

    def test_follow_already_following_returns_400(self, client):
        setup_user(client, "follow_dup_target")
        headers = setup_user(client, "follow_dup")
        client.post("/follow/follow_dup_target", headers=headers)

        res = client.post("/follow/follow_dup_target", headers=headers)
        assert res.status_code == 400
        assert "already" in res.json()["detail"].lower()

    def test_follow_requires_auth(self, client):
        res = client.post("/follow/someone")
        assert res.status_code == 401

    def test_unfollow_response_schema(self, client):
        setup_user(client, "unfollow_target")
        headers = setup_user(client, "unfollow_api")
        client.post("/follow/unfollow_target", headers=headers)

        res = client.post("/follow/un/unfollow_target", headers=headers)
        assert res.status_code == 200
        assert "unfollowed" in res.json()["message"]

    def test_unfollow_not_following_returns_400(self, client):
        setup_user(client, "unf_target")
        headers = setup_user(client, "unf_api")

        res = client.post("/follow/un/unf_target", headers=headers)
        assert res.status_code == 400
        assert "not following" in res.json()["detail"].lower()

    def test_unfollow_nonexistent_returns_404(self, client):
        headers = setup_user(client, "unf_ghost")
        res = client.post("/follow/un/nonexistent_user", headers=headers)
        assert res.status_code == 404

    def test_unfollow_requires_auth(self, client):
        res = client.post("/follow/un/someone")
        assert res.status_code == 401
