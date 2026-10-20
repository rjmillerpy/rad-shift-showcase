"""Tests for app/common/deps.py: the current-user dependencies, through real endpoints.

optional_user  -> GET  /posts/           (public read)
required_user  -> GET  /posts/saved      (needs a login)
verified_user  -> POST /posts/like/{id}  (needs a verified email)
"""

import pytest

from app.auth.models import User
from app.common.auth_jwt import AuthJWT


def _token_headers(subject: str) -> dict:
    return {"Authorization": f"Bearer {AuthJWT().create_access_token(subject=subject)}"}


class TestOptionalUser:
    def test_anonymous_request_is_served(self, client):
        assert client.get("/posts/").status_code == 200

    @pytest.mark.parametrize(
        "headers",
        [{"Authorization": "Bearer not.a.token"}, {"Authorization": "Token abc"}],
        ids=["invalid-token", "malformed-header"],
    )
    def test_a_bad_token_is_treated_as_anonymous(self, client, headers):
        assert client.get("/posts/", headers=headers).status_code == 200

    def test_token_for_a_deleted_user_is_treated_as_anonymous(self, client):
        assert client.get("/posts/", headers=_token_headers("ghost")).status_code == 200

    def test_a_valid_token_personalises_the_response(
        self, client, create_user, create_post, auth_header
    ):
        author = create_user(username="author")
        create_post(user=author, text="mine")

        as_author = client.get("/posts/", headers=auth_header("author")).json()["posts"][0]
        as_anonymous = client.get("/posts/").json()["posts"][0]

        assert as_author["is_me"] is True
        assert as_anonymous["is_me"] is False


class TestRequiredUser:
    def test_valid_user_is_let_through(self, client, create_user, auth_header):
        create_user(username="reader")
        assert client.get("/posts/saved", headers=auth_header("reader")).status_code == 200

    def test_missing_token_is_401(self, client):
        assert client.get("/posts/saved").status_code == 401

    def test_invalid_token_is_422(self, client):
        resp = client.get("/posts/saved", headers={"Authorization": "Bearer not.a.token"})
        assert resp.status_code == 422

    def test_token_for_a_deleted_user_is_404(self, client):
        resp = client.get("/posts/saved", headers=_token_headers("ghost"))
        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"


class TestVerifiedUser:
    @pytest.fixture()
    def post_id(self, create_user, create_post):
        return create_post(user=create_user(username="author"), text="like me").id

    def test_verified_user_is_let_through(self, client, create_user, auth_header, post_id):
        create_user(username="fan")
        assert client.post(f"/posts/like/{post_id}", headers=auth_header("fan")).status_code == 200

    def test_unverified_user_is_403(self, client, create_user, auth_header, db_session, post_id):
        create_user(username="newbie")
        # Test users are auto-verified on insert; undo that for this one.
        db_session.query(User).filter_by(username="newbie").update({"email_verified": False})
        db_session.commit()

        resp = client.post(f"/posts/like/{post_id}", headers=auth_header("newbie"))

        assert resp.status_code == 403
        assert "verify your email" in resp.json()["detail"]

    def test_missing_token_is_401_before_the_verification_check(self, client, post_id):
        assert client.post(f"/posts/like/{post_id}").status_code == 401
