"""Tests for app/posts — CRUD endpoints, drafts, replies, following feed."""

import json


class TestGetPosts:
    def test_get_posts_anon(self, client, create_user, create_post):
        user = create_user()
        create_post(user=user, text="public post")
        resp = client.get("/posts/")
        assert resp.status_code == 200
        posts = resp.json()["posts"]
        assert len(posts) == 1
        assert posts[0]["text"] == "public post"

    def test_get_posts_authenticated(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        create_post(user=user, text="alice post")
        resp = client.get("/posts/", headers=auth_header("alice"))
        assert resp.status_code == 200
        posts = resp.json()["posts"]
        assert len(posts) == 1

    def test_get_posts_excludes_drafts(self, client, create_user, create_post):
        user = create_user()
        create_post(user=user, text="public")
        create_post(user=user, text="draft", is_draft=True)
        resp = client.get("/posts/")
        assert len(resp.json()["posts"]) == 1

    def test_get_posts_excludes_replies(self, client, create_user, create_post):
        user = create_user()
        parent = create_post(user=user, text="parent")
        create_post(user=user, text="reply", is_reply=True, parent_post_id=parent.id)
        resp = client.get("/posts/")
        # Only the parent should appear (replies are filtered by is_reply==False)
        assert len(resp.json()["posts"]) == 1


class TestAddPost:
    def test_add_post_success(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post(
            "/posts/add",
            data={"text": "my first post", "post_metadata": "{}"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Post created"

    def test_add_post_with_metadata_tags(self, client, create_user, auth_header):
        create_user(username="alice")
        meta = json.dumps({"tags": "python|fastapi"})
        resp = client.post(
            "/posts/add",
            data={"text": "tagged post", "post_metadata": meta},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200

    def test_add_post_with_tagged_users(self, client, create_user, auth_header):
        create_user(username="alice")
        create_user(username="bob")
        meta = json.dumps({"tagged_users": ["bob", "nonexistent"]})
        resp = client.post(
            "/posts/add",
            data={"text": "tagging", "post_metadata": meta},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200

    def test_add_post_invalid_metadata(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post(
            "/posts/add",
            data={"text": "bad meta", "post_metadata": "not-json!!!"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 400
        assert "Invalid" in resp.json()["detail"]

    def test_add_draft(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post(
            "/posts/add",
            data={"text": "draft post", "post_metadata": "{}", "is_draft": "true"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Draft saved"

    def test_add_reply(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        parent = create_post(user=user, text="parent")
        resp = client.post(
            "/posts/add",
            data={
                "text": "reply text",
                "post_metadata": "{}",
                "is_reply": "true",
                "parent_post_id": str(parent.id),
            },
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200

    def test_add_post_text_too_long(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post(
            "/posts/add",
            data={"text": "x" * 5001, "post_metadata": "{}"},
            headers=auth_header("alice"),
        )
        assert resp.status_code == 400
        assert "5000" in resp.json()["detail"]

    def test_add_post_no_auth(self, client):
        resp = client.post("/posts/add", data={"text": "no auth", "post_metadata": "{}"})
        assert resp.status_code in (401, 422)


class TestDrafts:
    def test_get_drafts_empty(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.get("/posts/drafts", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert resp.json()["drafts"] == []

    def test_get_drafts_with_draft(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        create_post(user=user, text="my draft", is_draft=True)
        resp = client.get("/posts/drafts", headers=auth_header("alice"))
        assert len(resp.json()["drafts"]) == 1


class TestPublishDraft:
    def test_publish_draft_success(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        draft = create_post(user=user, text="draft", is_draft=True)
        resp = client.post(
            f"/posts/drafts/publish/{draft.id}",
            headers=auth_header("alice"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    def test_publish_already_published(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        post = create_post(user=user, text="not a draft", is_draft=False)
        resp = client.post(
            f"/posts/drafts/publish/{post.id}",
            headers=auth_header("alice"),
        )
        assert resp.status_code == 400
        assert "already published" in resp.json()["detail"]

    def test_publish_not_found(self, client, create_user, auth_header):
        create_user(username="alice")
        resp = client.post(
            "/posts/drafts/publish/9999",
            headers=auth_header("alice"),
        )
        assert resp.status_code == 404


class TestReplies:
    def test_get_replies(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        parent = create_post(user=user, text="parent")
        create_post(user=user, text="reply 1", is_reply=True, parent_post_id=parent.id)
        create_post(user=user, text="reply 2", is_reply=True, parent_post_id=parent.id)
        resp = client.get(f"/posts/{parent.id}/replies")
        assert resp.status_code == 200
        assert len(resp.json()["replies"]) == 2

    def test_get_replies_authenticated(self, client, create_user, create_post, auth_header):
        user = create_user(username="alice")
        parent = create_post(user=user, text="parent")
        create_post(user=user, text="reply", is_reply=True, parent_post_id=parent.id)
        resp = client.get(f"/posts/{parent.id}/replies", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert len(resp.json()["replies"]) == 1

    def test_get_replies_empty(self, client, create_user, create_post):
        user = create_user()
        post = create_post(user=user)
        resp = client.get(f"/posts/{post.id}/replies")
        assert resp.json()["replies"] == []


class TestFollowingPosts:
    def test_following_posts(self, client, create_user, create_post, auth_header, db_session):
        alice = create_user(username="alice")
        bob = create_user(username="bob")
        create_post(user=bob, text="bob post")
        # alice follows bob
        alice.followed.append(bob)
        db_session.commit()
        resp = client.get("/posts/following", headers=auth_header("alice"))
        assert resp.status_code == 200
        assert len(resp.json()["posts"]) == 1

    def test_following_posts_no_auth(self, client):
        resp = client.get("/posts/following")
        assert resp.status_code in (401, 422)
