"""Black-box tests for post models — exercised through the HTTP API."""

import pytest


class TestCreatePost:
    def test_post_appears_in_feed(self, client, create_user, auth_header):
        create_user("alice")
        headers = auth_header("alice")

        resp = client.post(
            "/posts/add",
            data={"text": "Hello world"},
            headers=headers,
        )
        assert resp.status_code == 200

        feed = client.get("/posts/", headers=headers).json()
        assert any(p["text"] == "Hello world" for p in feed["posts"])

    def test_post_has_expected_fields(self, client, create_user, create_post, auth_header):
        user = create_user("alice")
        post = create_post(user, text="Check fields")
        headers = auth_header("alice")

        resp = client.get(f"/posts/{post.id}", headers=headers)
        assert resp.status_code == 200
        p = resp.json()["post"]
        assert p["text"] == "Check fields"
        assert p["username"] == "alice"
        assert "likes" in p
        assert "unix_timestamp" in p

    @pytest.mark.parametrize(
        "text",
        ["Short", "A" * 1000, "With\nnewlines\nand\ttabs"],
    )
    def test_various_post_texts(self, client, create_user, auth_header, text):
        create_user("poster")
        headers = auth_header("poster")

        resp = client.post(
            "/posts/add",
            data={"text": text},
            headers=headers,
        )
        assert resp.status_code == 200


class TestCreateReply:
    def test_reply_has_parent_post_id(self, client, create_user, create_post, auth_header):
        user = create_user("alice")
        parent = create_post(user, text="Parent post")
        headers = auth_header("alice")

        resp = client.post(
            "/posts/add",
            data={
                "text": "This is a reply",
                "parent_post_id": str(parent.id),
                "is_reply": "true",
            },
            headers=headers,
        )
        assert resp.status_code == 200

        # Fetch replies for the parent
        replies_resp = client.get(f"/posts/{parent.id}/replies", headers=headers)
        assert replies_resp.status_code == 200
        replies = replies_resp.json()["replies"]
        assert any(r["text"] == "This is a reply" for r in replies)

    def test_parent_post_not_in_replies_of_wrong_parent(
        self, client, create_user, create_post, auth_header
    ):
        user = create_user("alice")
        post_a = create_post(user, text="Post A")
        post_b = create_post(user, text="Post B")
        headers = auth_header("alice")

        client.post(
            "/posts/add",
            data={
                "text": "Reply to A",
                "parent_post_id": str(post_a.id),
                "is_reply": "true",
            },
            headers=headers,
        )

        replies_b = client.get(f"/posts/{post_b.id}/replies", headers=headers).json()["replies"]
        assert not any(r["text"] == "Reply to A" for r in replies_b)


class TestPostDrafts:
    def test_draft_not_in_public_feed(self, client, create_user, auth_header):
        create_user("alice")
        headers = auth_header("alice")

        client.post(
            "/posts/add",
            data={"text": "My draft", "is_draft": "true"},
            headers=headers,
        )

        feed = client.get("/posts/", headers=headers).json()
        assert not any(p["text"] == "My draft" for p in feed["posts"])

    def test_draft_appears_in_drafts_endpoint(self, client, create_user, auth_header):
        create_user("alice")
        headers = auth_header("alice")

        client.post(
            "/posts/add",
            data={"text": "My draft", "is_draft": "true"},
            headers=headers,
        )

        drafts = client.get("/posts/drafts", headers=headers).json()
        assert any(d["text"] == "My draft" for d in drafts["drafts"])
