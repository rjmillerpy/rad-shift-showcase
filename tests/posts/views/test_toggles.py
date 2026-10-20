"""Tests for app/posts — toggle actions (like/laugh/repost/save/share/slop)."""

import pytest


class TestToggles:
    @pytest.mark.parametrize(
        "endpoint,action_field,count_field,active_value",
        [
            ("/posts/like/{}", "action", "likes", "liked"),
            ("/posts/laugh/{}", "action", "laughs", "laughed"),
            ("/posts/repost/{}", "action", "reposts", "re-posted"),
            ("/posts/save/{}", "action", "saves", "saved"),
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_toggle_on(
        self,
        client,
        create_user,
        create_post,
        auth_header,
        endpoint,
        action_field,
        count_field,
        active_value,
    ):
        user = create_user(username="toggler")
        post = create_post(user=user)
        resp = client.post(
            endpoint.format(post.id),
            headers=auth_header("toggler"),
        )
        assert resp.status_code == 200
        assert resp.json()[action_field] == active_value
        assert resp.json()[count_field] >= 1


class TestToggleLike:
    def test_like_on(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(f"/posts/like/{post.id}", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert resp.json()["action"] == "liked"
        assert resp.json()["likes"] == 1

    def test_like_off(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        headers = auth_header("alice")
        client.post(f"/posts/like/{post.id}", headers=headers)
        resp = client.post(f"/posts/like/{post.id}", headers=headers)
        assert resp.json()["action"] == "unliked"
        assert resp.json()["likes"] == 0

    def test_like_post_not_found(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post("/posts/like/9999", headers=auth_header("alice"))
        assert resp.status_code == 404


class TestToggleRepost:
    def test_repost_on(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(f"/posts/repost/{post.id}", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert resp.json()["action"] == "re-posted"
        assert resp.json()["reposts"] == 1

    def test_repost_off(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        headers = auth_header("alice")
        client.post(f"/posts/repost/{post.id}", headers=headers)
        resp = client.post(f"/posts/repost/{post.id}", headers=headers)
        assert resp.json()["action"] == "un-re-posted"
        assert resp.json()["reposts"] == 0

    def test_repost_not_found(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post("/posts/repost/9999", headers=auth_header("alice"))
        assert resp.status_code == 404


class TestShare:
    def test_share_authenticated(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(f"/posts/share/{post.id}", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert resp.json()["shares"] == 1

    def test_share_anon(self, client, create_user, create_post):
        user = create_user()
        post = create_post(user=user)
        resp = client.post(f"/posts/share/{post.id}")
        assert resp.status_code == 200
        assert resp.json()["shares"] == 1

    def test_share_post_not_found(self, client):
        resp = client.post("/posts/share/9999")
        assert resp.status_code == 404


class TestToggleLaugh:
    def test_laugh_on(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(f"/posts/laugh/{post.id}", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert resp.json()["action"] == "laughed"
        assert resp.json()["laughs"] == 1

    def test_laugh_off(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        headers = auth_header("alice")
        client.post(f"/posts/laugh/{post.id}", headers=headers)
        resp = client.post(f"/posts/laugh/{post.id}", headers=headers)
        assert resp.json()["action"] == "unlaughed"
        assert resp.json()["laughs"] == 0

    def test_laugh_post_not_found(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post("/posts/laugh/9999", headers=auth_header("alice"))
        assert resp.status_code == 404

    def test_laugh_requires_auth(self, client, create_user, create_post):
        user = create_user()
        post = create_post(user=user)
        resp = client.post(f"/posts/laugh/{post.id}")
        assert resp.status_code == 401

    def test_laugh_idempotent_toggle(self, client, create_user, create_post, auth_header):
        """Laughing twice returns to 0 — no negative counts."""
        user = create_user(username="alice")
        post = create_post(user=user)
        headers = auth_header("alice")
        client.post(f"/posts/laugh/{post.id}", headers=headers)
        client.post(f"/posts/laugh/{post.id}", headers=headers)
        resp = client.post(f"/posts/laugh/{post.id}", headers=headers)
        assert resp.json()["laughs"] == 1

    def test_laugh_appears_in_feed(self, client, create_user, create_post, auth_header):
        """laughed_by_me and laughs count appear in the feed response."""
        user = create_user(username="alice")
        post = create_post(user=user, text="Funny post")
        headers = auth_header("alice")
        client.post(f"/posts/laugh/{post.id}", headers=headers)

        resp = client.get("/posts/", headers=headers)
        feed_post = resp.json()["posts"][0]
        assert feed_post["laughs"] == 1
        assert feed_post["laughed_by_me"] is True

    def test_laugh_by_other_user(self, client, create_user, create_post, auth_header):
        """Another user's laugh increments count but doesn't affect first user's laughed_by_me."""
        alice = create_user(username="alice")
        create_user(username="bob")
        post = create_post(user=alice, text="Multi laugh")
        client.post(f"/posts/laugh/{post.id}", headers=auth_header("alice"))
        client.post(f"/posts/laugh/{post.id}", headers=auth_header("bob"))

        resp = client.get("/posts/", headers=auth_header("alice"))
        feed_post = resp.json()["posts"][0]
        assert feed_post["laughs"] == 2
        assert feed_post["laughed_by_me"] is True

        resp = client.get("/posts/", headers=auth_header("bob"))
        feed_post = resp.json()["posts"][0]
        assert feed_post["laughed_by_me"] is True

    def test_laugh_counter_never_negative(
        self, client, create_user, create_post, auth_header, db_session
    ):
        """Even if the counter gets corrupted, the atomic SQL prevents negative values."""
        from app.posts.models import PostModel

        user = create_user(username="alice")
        post = create_post(user=user)
        # Force counter to 0
        db_session.execute(
            PostModel.__table__.update().where(PostModel.id == post.id).values(laughs=0)
        )
        db_session.commit()
        # Laugh then unlaugh — should stay at 0
        headers = auth_header("alice")
        client.post(f"/posts/laugh/{post.id}", headers=headers)
        resp = client.post(f"/posts/laugh/{post.id}", headers=headers)
        assert resp.json()["laughs"] == 0


class TestToggleSave:
    def test_save_on(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(f"/posts/save/{post.id}", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert resp.json()["action"] == "saved"
        assert resp.json()["saves"] == 1

    def test_save_off(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        headers = auth_header("alice")
        client.post(f"/posts/save/{post.id}", headers=headers)
        resp = client.post(f"/posts/save/{post.id}", headers=headers)
        assert resp.json()["action"] == "unsaved"
        assert resp.json()["saves"] == 0

    def test_save_not_found(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post("/posts/save/9999", headers=auth_header("alice"))
        assert resp.status_code == 404


class TestGetSaved:
    def test_get_saved_empty(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.get("/posts/saved", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert resp.json()["posts"] == []

    def test_get_saved_with_posts(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user, text="save me")
        headers = auth_header("alice")
        client.post(f"/posts/save/{post.id}", headers=headers)
        resp = client.get("/posts/saved", headers=headers)
        assert resp.status_code == 200
        posts = resp.json()["posts"]
        assert len(posts) == 1
        assert posts[0]["is_saved_by_me"] is True


class TestSlop:
    def test_mark_slop_new(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(
            f"/posts/slop/{post.id}",
            json={"reason": "AI generated"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_mark_slop_update(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        headers = auth_header("alice")
        client.post(f"/posts/slop/{post.id}", json={"reason": "AI"}, headers=headers)
        resp = client.post(
            f"/posts/slop/{post.id}",
            json={"reason": "updated reason"},
            headers=headers,
        )
        assert resp.json()["status"] == "updated"

    def test_mark_slop_missing_reason(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(
            f"/posts/slop/{post.id}",
            json={"reason": ""},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 422

    def test_mark_slop_no_reason_key(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user)
        resp = client.post(
            f"/posts/slop/{post.id}",
            json={},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 422

    def test_mark_slop_post_not_found(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post(
            "/posts/slop/9999",
            json={"reason": "bot"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 404

    def test_slopped_posts_excluded_from_feed(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user, text="sloppy")
        headers = auth_header("alice")
        client.post(f"/posts/slop/{post.id}", json={"reason": "spam"}, headers=headers)
        resp = client.get("/posts/", headers=headers)
        # The slopped post should be excluded for this user
        assert all(p["text"] != "sloppy" for p in resp.json()["posts"])
