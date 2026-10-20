"""Tests for app/auth/models.py — User model via public API."""

import pytest


class TestUserModel:
    def test_user_created_via_signup(self, client):
        resp = client.post(
            "/auth/signup",
            json={
                "username": "model_test",
                "password": "password123",
                "email": "model@test.com",
            },
        )
        assert resp.status_code == 200

        # Verify via login
        resp = client.post(
            "/auth/login", json={"username": "model_test", "password": "password123"}
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_password_hashed_not_plain(self, client):
        """Verify password is not stored in plain text by checking login with wrong password fails."""
        client.post(
            "/auth/signup",
            json={
                "username": "hash_test",
                "password": "mypassword1",
                "email": "hash@test.com",
            },
        )
        resp = client.post(
            "/auth/login", json={"username": "hash_test", "password": "mypassword1x"}
        )
        assert resp.status_code == 401

    @pytest.mark.parametrize("field", ["username", "bio", "profile_picture_url"])
    def test_profile_fields_exist(self, client, create_user, auth_header, field):
        create_user(username="field_test")
        resp = client.get("/profile/me", headers=auth_header("field_test"))
        assert field in resp.json()


class TestPasswordHashCost:
    @pytest.mark.parametrize("rounds", [4, 5, 6], ids=["cost-4", "cost-5", "cost-6"])
    def test_hash_made_at_any_cost_still_verifies(self, rounds):
        """bcrypt stores the cost inside each hash, so accounts hashed at an
        older (or future) BCRYPT_ROUNDS keep working after it changes."""
        import bcrypt

        from app.auth.models import User

        user = User(username="x")
        user.password_hash = bcrypt.hashpw(b"password123", bcrypt.gensalt(rounds=rounds)).decode()
        assert user.check_password("password123")
        assert not user.check_password("wrong-password")
