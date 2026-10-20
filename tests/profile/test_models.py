"""Tests for app/profile/models.py — User profile fields via public API."""


class TestProfileModel:
    def test_new_user_has_empty_bio(self, client, create_user, auth_header):
        create_user(username="bio_test")
        resp = client.get("/profile/me", headers=auth_header("bio_test"))
        assert resp.json().get("bio") in (None, "")

    def test_profile_has_posts_list(self, client, create_user, auth_header):
        create_user(username="posts_list")
        resp = client.get("/profile/me", headers=auth_header("posts_list"))
        assert isinstance(resp.json()["posts"], list)
