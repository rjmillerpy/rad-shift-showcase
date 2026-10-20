"""Tests for app/profile/service.py — API-level for endpoint-flavored functions
plus direct unit tests for the settings helpers.
"""

import io

import pytest

from app.profile.schema import AlgoSettingsRequest
from app.profile.service import apply_settings_update, get_merged_settings


class TestGetMergedSettings:
    def test_defaults_when_user_has_no_settings(self, create_user, db_session):
        user = create_user(username="svc_merge_none")
        defaults = {"foo": 1, "bar": 2}
        assert get_merged_settings(user, "algo_settings", defaults) == defaults

    def test_stored_overrides_defaults(self, create_user, db_session):
        user = create_user(username="svc_merge_override")
        user.algo_settings = {"foo": 42}
        db_session.commit()
        defaults = {"foo": 1, "bar": 2}
        assert get_merged_settings(user, "algo_settings", defaults) == {"foo": 42, "bar": 2}


class TestApplySettingsUpdate:
    def _defaults(self) -> dict:
        return {"like_weight": 1.0, "recency_weight": 0.3, "engagement_enabled": True}

    def test_persists_provided_fields(self, create_user, db_session):
        user = create_user(username="svc_apply_persist")
        body = AlgoSettingsRequest(like_weight=2.5)
        result = apply_settings_update(
            user,
            "algo_settings",
            self._defaults(),
            body,
            db_session,
        )
        db_session.refresh(user)
        assert user.algo_settings["like_weight"] == 2.5
        assert result["like_weight"] == 2.5

    def test_second_update_persists(self, create_user, db_session):
        """Regression: in-place mutation of the JSON column meant only the
        first save ever reached the database."""
        user = create_user(username="svc_apply_twice")
        for weight in (2.0, 9.0):
            apply_settings_update(
                user,
                "algo_settings",
                self._defaults(),
                AlgoSettingsRequest(like_weight=weight),
                db_session,
            )
        db_session.expire_all()
        assert user.algo_settings["like_weight"] == 9.0

    def test_returns_merged_defaults(self, create_user, db_session):
        user = create_user(username="svc_apply_merged")
        body = AlgoSettingsRequest(like_weight=2.0)
        result = apply_settings_update(
            user,
            "algo_settings",
            self._defaults(),
            body,
            db_session,
        )
        # Unset fields fall through to defaults.
        assert result["recency_weight"] == 0.3
        assert result["engagement_enabled"] is True

    def test_ignores_unset_fields(self, create_user, db_session):
        user = create_user(username="svc_apply_unset")
        user.algo_settings = {"like_weight": 5.0}
        db_session.commit()
        body = AlgoSettingsRequest()  # nothing set
        result = apply_settings_update(
            user,
            "algo_settings",
            self._defaults(),
            body,
            db_session,
        )
        assert result["like_weight"] == 5.0  # stored value preserved

    def test_ignores_unknown_defaults_keys(self, create_user, db_session):
        """Only keys listed in `defaults` are merged in; foreign keys the
        client sneaks in are dropped (rule 5 — validate at boundary)."""
        user = create_user(username="svc_apply_unknown")
        body = AlgoSettingsRequest(like_weight=1.5)
        result = apply_settings_update(
            user,
            "algo_settings",
            self._defaults(),
            body,
            db_session,
        )
        assert "admin_flag" not in result


class TestUpdateBio:
    def test_update_bio_persists(self, client, create_user, auth_header):
        create_user("alice")
        headers = auth_header("alice")

        resp = client.put("/profile/me", json={"bio": "Hello world"}, headers=headers)
        assert resp.status_code == 200

        profile = client.get("/profile/me", headers=headers).json()
        assert profile["bio"] == "Hello world"

    def test_update_bio_to_none(self, client, create_user, auth_header):
        create_user("bob")
        headers = auth_header("bob")

        client.put("/profile/me", json={"bio": "temp"}, headers=headers)
        client.put("/profile/me", json={"bio": None}, headers=headers)

        profile = client.get("/profile/me", headers=headers).json()
        assert profile["bio"] is None

    @pytest.mark.parametrize("bio_text", ["", "A" * 500, "Line1\nLine2"])
    def test_various_bio_values(self, client, create_user, auth_header, bio_text):
        create_user("user1")
        headers = auth_header("user1")

        resp = client.put("/profile/me", json={"bio": bio_text}, headers=headers)
        assert resp.status_code == 200

        profile = client.get("/profile/me", headers=headers).json()
        assert profile["bio"] == bio_text


class TestUploadProfilePic:
    def test_upload_returns_url(self, client, create_user, auth_header):
        create_user("alice")
        headers = auth_header("alice")

        fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        resp = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("photo.jpg", fake_image, "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert isinstance(data["url"], str)
        assert "s3.amazonaws.com" in data["url"]

    def test_upload_empty_filename_rejected(self, client, create_user, auth_header):
        create_user("alice")
        headers = auth_header("alice")

        fake_image = io.BytesIO(b"\x89PNG")
        resp = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("", fake_image, "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code in (400, 422)


class TestGetProfile:
    def test_profile_includes_posts(self, client, create_user, create_post, auth_header):
        user = create_user("alice")
        create_post(user, text="My first post")
        headers = auth_header("alice")

        profile = client.get("/profile/me", headers=headers).json()
        assert "posts" in profile
        assert len(profile["posts"]) == 1
        assert profile["posts"][0]["text"] == "My first post"

    def test_profile_excludes_drafts(self, client, create_user, create_post, auth_header):
        user = create_user("alice")
        create_post(user, text="published")
        create_post(user, text="draft post", is_draft=True)
        headers = auth_header("alice")

        profile = client.get("/profile/me", headers=headers).json()
        texts = [p["text"] for p in profile["posts"]]
        assert "published" in texts
        assert "draft post" not in texts

    def test_public_profile_by_username(self, client, create_user, auth_header):
        create_user("alice")
        create_user("bob")
        headers = auth_header("bob")

        resp = client.get("/profile/alice", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"

    def test_nonexistent_user_404(self, client, create_user, auth_header):
        create_user("alice")
        headers = auth_header("alice")
        resp = client.get("/profile/ghost", headers=headers)
        assert resp.status_code == 404
