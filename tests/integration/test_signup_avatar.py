"""Integration test: signing up a new user attaches an avatar URL to their profile.

This is cross-cutting (auth signup service invokes the avatar generator with an
S3 upload). Kept in tests/integration/ per the test-structure rule for
cross-domain flows.
"""


class TestSignupGeneratesAvatar:
    def test_new_user_has_profile_picture_after_signup(self, client):
        resp = client.post(
            "/auth/signup",
            json={
                "username": "avatar_test",
                "password": "password123",
                "email": "avatar_test@test.com",
            },
        )
        assert resp.status_code == 200

        login = client.post(
            "/auth/login",
            json={
                "username": "avatar_test",
                "password": "password123",
            },
        )
        token = login.json()["access_token"]
        profile = client.get(
            "/profile/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert profile.status_code == 200
        assert profile.json()["profile_picture_url"] is not None
