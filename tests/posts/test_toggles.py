"""Tests for app/posts/toggles.py — like, laugh, repost, save, share, slop."""

import pytest

from app.engagement.schema import PostEventType


class TestToggleEndpoints:
    """Parametrized tests for all toggle endpoints."""

    @pytest.mark.parametrize(
        "endpoint,count_field,active_action",
        [
            ("/posts/like/{}", "likes", "liked"),
            ("/posts/laugh/{}", "laughs", "laughed"),
            ("/posts/repost/{}", "reposts", "re-posted"),
            ("/posts/save/{}", "saves", "saved"),
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_toggle_on(
        self, client, create_user, create_post, auth_header, endpoint, count_field, active_action
    ):
        user = create_user(username="toggler")
        post = create_post(user=user)
        resp = client.post(endpoint.format(post.id), headers=auth_header("toggler"))
        assert resp.status_code == 200
        assert resp.json()["action"] == active_action
        assert resp.json()[count_field] >= 1

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/posts/like/{}",
            "/posts/laugh/{}",
            "/posts/repost/{}",
            "/posts/save/{}",
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_toggle_off(self, client, create_user, create_post, auth_header, endpoint):
        user = create_user(username="toggler_off")
        post = create_post(user=user)
        headers = auth_header("toggler_off")
        client.post(endpoint.format(post.id), headers=headers)
        resp = client.post(endpoint.format(post.id), headers=headers)
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/posts/like/{}",
            "/posts/laugh/{}",
            "/posts/repost/{}",
            "/posts/save/{}",
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_toggle_not_found(self, client, create_user, auth_header, endpoint):
        create_user(username="toggler_nf")
        resp = client.post(endpoint.format(99999), headers=auth_header("toggler_nf"))
        assert resp.status_code == 404

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/posts/like/1",
            "/posts/laugh/1",
            "/posts/repost/1",
            "/posts/save/1",
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_toggle_requires_auth(self, client, endpoint):
        resp = client.post(endpoint)
        assert resp.status_code in (401, 422)


class TestShare:
    def test_share_creates_link(self, client, create_user, create_post, auth_header):
        user = create_user(username="sharer")
        post = create_post(user=user)
        resp = client.post(f"/posts/share/{post.id}", headers=auth_header("sharer"))
        assert resp.status_code == 200
        assert "share_url" in resp.json()
        assert resp.json()["shares"] >= 1

    def test_share_not_found(self, client, create_user, auth_header):
        create_user(username="sharer_nf")
        resp = client.post("/posts/share/99999", headers=auth_header("sharer_nf"))
        assert resp.status_code == 404


class TestSlop:
    def test_slop_success(self, client, create_user, create_post, auth_header):
        user = create_user(username="slopper")
        post = create_post(user=user)
        resp = client.post(
            f"/posts/slop/{post.id}",
            json={"reason": "AI generated"},
            headers=auth_header("slopper"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.parametrize(
        "payload,expected_status",
        [
            ({"reason": ""}, 422),
            ({}, 422),
            ({"reason": None}, 422),
        ],
        ids=["empty-reason", "missing-reason", "null-reason"],
    )
    def test_slop_validation(
        self, client, create_user, create_post, auth_header, payload, expected_status
    ):
        user = create_user(username="slop_val")
        post = create_post(user=user)
        resp = client.post(
            f"/posts/slop/{post.id}",
            json=payload,
            headers=auth_header("slop_val"),
        )
        assert resp.status_code == expected_status


class TestEventsPublished:
    """Each committed toggle publishes one post event (app/engagement/, item 29b)."""

    @pytest.mark.parametrize(
        "endpoint,on,off",
        [
            ("/posts/like/{}", PostEventType.LIKED, PostEventType.UNLIKED),
            ("/posts/laugh/{}", PostEventType.LAUGHED, PostEventType.UNLAUGHED),
            ("/posts/repost/{}", PostEventType.REPOSTED, PostEventType.UNREPOSTED),
            ("/posts/save/{}", PostEventType.SAVED, PostEventType.UNSAVED),
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_on_then_off(
        self, client, create_user, create_post, auth_header, published, endpoint, on, off
    ):
        user = create_user(username="evented")
        post = create_post(user=user)

        client.post(endpoint.format(post.id), headers=auth_header("evented"))
        client.post(endpoint.format(post.id), headers=auth_header("evented"))

        assert [(e.type, e.post_id, e.user_id) for e in published.events()] == [
            (on, post.id, user.id),
            (off, post.id, user.id),
        ]

    def test_an_anonymous_share_has_no_user(self, client, create_user, create_post, published):
        post = create_post(user=create_user(username="sharee"))

        client.post(f"/posts/share/{post.id}")

        ((event_type, user_id),) = [(e.type, e.user_id) for e in published.events()]
        assert (event_type, user_id) == (PostEventType.SHARED, None)

    def test_a_duplicate_share_publishes_nothing(
        self, client, create_user, create_post, auth_header, published
    ):
        user = create_user(username="twice")
        post = create_post(user=user)

        client.post(f"/posts/share/{post.id}", headers=auth_header("twice"))
        client.post(f"/posts/share/{post.id}", headers=auth_header("twice"))

        assert len(published.events()) == 1

    def test_a_missing_post_publishes_nothing(self, client, create_user, auth_header, published):
        create_user(username="nobody")

        assert client.post("/posts/like/999", headers=auth_header("nobody")).status_code == 404
        assert published.events() == []

    def test_slop_marks_publish_nothing(
        self, client, create_user, create_post, auth_header, published
    ):
        user = create_user(username="slopper")
        post = create_post(user=user)

        client.post(
            f"/posts/slop/{post.id}", json={"reason": "spam"}, headers=auth_header("slopper")
        )

        assert published.events() == []
