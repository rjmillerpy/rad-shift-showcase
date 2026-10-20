"""API-level tests for app/follow/views.py."""

import pytest

from app.auth.constants import MAX_USERNAME_LEN


class TestFollow:
    def test_success(self, client, create_user, auth_header):
        create_user(username="alice")
        create_user(username="bob")
        resp = client.post("/follow/bob", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert "following" in resp.json()["message"].lower()

    def test_already_following(self, client, create_user, auth_header, db_session):
        alice = create_user(username="alice_af")
        bob = create_user(username="bob_af")
        alice.followed.append(bob)
        db_session.commit()
        resp = client.post("/follow/bob_af", headers=auth_header("alice_af"))
        assert resp.status_code == 400
        assert "already" in resp.json()["detail"].lower()

    def test_follow_self_rejected(self, client, create_user, auth_header):
        create_user(username="alice_self")
        resp = client.post("/follow/alice_self", headers=auth_header("alice_self"))
        assert resp.status_code == 400
        assert "yourself" in resp.json()["detail"].lower()

    def test_target_not_found(self, client, create_user, auth_header):
        create_user(username="alice_ghost")
        resp = client.post("/follow/ghost_user_xyz", headers=auth_header("alice_ghost"))
        assert resp.status_code == 404

    def test_no_auth_401(self, client, create_user):
        create_user(username="bob_noauth")
        resp = client.post("/follow/bob_noauth")
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        "username,expected_status",
        [
            ("", 404),  # empty path collapses; router returns 404 for /follow/
            ("x" * (MAX_USERNAME_LEN + 1), 422),
        ],
        ids=["empty_path", "too_long"],
    )
    def test_username_bounds_enforced(
        self,
        client,
        create_user,
        auth_header,
        username,
        expected_status,
    ):
        create_user(username="alice_bounds")
        resp = client.post(f"/follow/{username}", headers=auth_header("alice_bounds"))
        assert resp.status_code == expected_status


class TestUnfollow:
    def test_success(self, client, create_user, auth_header, db_session):
        alice = create_user(username="alice_uf")
        bob = create_user(username="bob_uf")
        alice.followed.append(bob)
        db_session.commit()
        resp = client.post("/follow/un/bob_uf", headers=auth_header("alice_uf"))
        assert resp.status_code == 200
        assert "unfollowed" in resp.json()["message"].lower()

    def test_not_following_returns_400(self, client, create_user, auth_header):
        create_user(username="alice_nf")
        create_user(username="bob_nf")
        resp = client.post("/follow/un/bob_nf", headers=auth_header("alice_nf"))
        assert resp.status_code == 400
        assert "not following" in resp.json()["detail"].lower()

    def test_target_not_found(self, client, create_user, auth_header):
        create_user(username="alice_ug")
        resp = client.post("/follow/un/ghost_xyz", headers=auth_header("alice_ug"))
        assert resp.status_code == 404

    def test_no_auth_401(self, client, create_user):
        create_user(username="bob_uunoauth")
        resp = client.post("/follow/un/bob_uunoauth")
        assert resp.status_code == 401


class TestFollowingFeed:
    """Cross-check: the /posts/following endpoint reflects the follow state."""

    def test_feed_shows_followed_only(
        self,
        client,
        create_user,
        create_post,
        auth_header,
    ):
        create_user(username="alice_feed")
        bob = create_user(username="bob_feed")
        carol = create_user(username="carol_feed")
        create_post(bob, text="Bob's post")
        create_post(carol, text="Carol's post")
        headers = auth_header("alice_feed")
        client.post("/follow/bob_feed", headers=headers)

        resp = client.get("/posts/following", headers=headers)
        texts = [p["text"] for p in resp.json()["posts"]]
        assert "Bob's post" in texts
        assert "Carol's post" not in texts

    def test_empty_when_not_following_anyone(self, client, create_user, auth_header):
        create_user(username="alice_empty")
        resp = client.get("/posts/following", headers=auth_header("alice_empty"))
        assert resp.status_code == 200
        assert resp.json()["posts"] == []

    def test_unfollow_removes_from_feed(
        self,
        client,
        create_user,
        create_post,
        auth_header,
    ):
        create_user(username="alice_ufeed")
        bob = create_user(username="bob_ufeed")
        create_post(bob, text="Bob's post")
        headers = auth_header("alice_ufeed")
        client.post("/follow/bob_ufeed", headers=headers)
        client.post("/follow/un/bob_ufeed", headers=headers)
        resp = client.get("/posts/following", headers=headers)
        assert not any(p["text"] == "Bob's post" for p in resp.json()["posts"])
