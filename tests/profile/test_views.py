"""Tests for app/profile – get/update my profile, public profile, upload pic."""

import io
from unittest.mock import patch


class TestGetMyProfile:
    def test_get_my_profile(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.get("/profile/me", headers=auth_header("alice"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "alice"
        assert "bio" in data
        assert "posts" in data

    def test_get_my_profile_no_auth(self, client):
        resp = client.get("/profile/me")
        assert resp.status_code in (401, 422)


class TestUpdateProfile:
    def test_update_bio(self, client, create_user, auth_header):
        create_user(username="alice")
        headers = auth_header("alice")
        resp = client.put("/profile/me", json={"bio": "new bio"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "Profile updated"

        # Verify the change persisted
        profile = client.get("/profile/me", headers=headers).json()
        assert profile["bio"] == "new bio"

    def test_update_profile_picture_url(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.put(
            "/profile/me",
            json={"profile_picture_url": "https://example.com/pic.jpg"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200


class TestGetUserProfile:
    def test_get_existing_user_profile(self, client, create_user):
        create_user(username="alice")
        resp = client.get("/profile/alice")
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"

    def test_get_nonexistent_user_profile(self, client):
        resp = client.get("/profile/ghost")
        assert resp.status_code == 404

    def test_username_path_cap_enforced(self, client):
        """`/{username}` must reject usernames beyond the configured cap
        (rule 5/11 — validate at boundary)."""
        from app.profile.constants import MAX_USERNAME_PATH_LEN

        resp = client.get(f"/profile/{'x' * (MAX_USERNAME_PATH_LEN + 1)}")
        assert resp.status_code == 422


class TestUploadProfilePicture:
    def test_upload_success(self, client, create_user, auth_header):
        create_user(username="alice")
        file_data = io.BytesIO(b"fakejpegdata")
        resp = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("avatar.jpg", file_data, "image/jpeg")},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200
        assert "url" in resp.json()

    def test_upload_empty_filename(self, client, create_user, auth_header):
        create_user(username="alice")
        file_data = io.BytesIO(b"fakejpegdata")
        resp = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("", file_data, "image/jpeg")},
            headers=auth_header("alice"),
        )
        # FastAPI/starlette may return 400 or 422 for empty filename
        assert resp.status_code in (400, 422)

    def test_upload_no_auth(self, client):
        file_data = io.BytesIO(b"fakejpegdata")
        resp = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("pic.jpg", file_data, "image/jpeg")},
        )
        assert resp.status_code in (401, 422)

    def test_upload_s3_failure(self, client, create_user, auth_header):
        create_user(username="alice")
        file_data = io.BytesIO(b"fakejpegdata")
        with patch(
            "app.profile.service.upload_fileobj_to_s3",
            side_effect=Exception("S3 down"),
        ):
            resp = client.post(
                "/profile/me/upload-profile-pic",
                files={"file": ("avatar.jpg", file_data, "image/jpeg")},
                headers=auth_header("alice"),
            )
            assert resp.status_code == 500
