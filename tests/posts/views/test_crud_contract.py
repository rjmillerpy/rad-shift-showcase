"""API contract tests for /posts write endpoints (add, publish drafts)."""

import io

from tests.helpers import make_post, setup_user


class TestPostsAddAPI:
    """POST /posts/add."""

    def test_add_post_response_schema(self, client):
        headers = setup_user(client, "add_schema")
        res = make_post(client, headers)
        assert res.status_code == 200
        body = res.json()
        assert "message" in body
        assert body["message"] == "Post created"
        assert "image_url" in body
        assert "video_url" in body
        assert "audio_url" in body

    def test_add_post_requires_auth(self, client):
        res = client.post("/posts/add", data={"text": "no auth", "post_metadata": "{}"})
        assert res.status_code == 401

    def test_add_post_text_required(self, client):
        headers = setup_user(client, "no_text")
        res = client.post("/posts/add", data={"post_metadata": "{}"}, headers=headers)
        assert res.status_code == 422

    def test_add_post_text_max_length(self, client):
        headers = setup_user(client, "long_text")
        res = make_post(client, headers, text="x" * 5001)
        assert res.status_code == 400
        assert "5000" in res.json()["detail"]

    def test_add_post_text_at_max_length(self, client):
        headers = setup_user(client, "exact_len")
        res = make_post(client, headers, text="x" * 5000)
        assert res.status_code == 200

    def test_add_post_invalid_metadata(self, client):
        headers = setup_user(client, "bad_meta")
        res = client.post(
            "/posts/add",
            data={"text": "Bad metadata", "post_metadata": "not valid json{{"},
            headers=headers,
        )
        assert res.status_code == 400
        assert "metadata" in res.json()["detail"].lower()

    def test_add_post_as_draft(self, client):
        headers = setup_user(client, "drafter_api")
        res = make_post(client, headers, text="Draft", is_draft="true")
        assert res.status_code == 200
        assert res.json()["message"] == "Draft saved"

    def test_add_post_as_reply(self, client):
        headers = setup_user(client, "replier_api")
        make_post(client, headers, text="Parent")
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(
            "/posts/add",
            data={
                "text": "Reply text",
                "post_metadata": "{}",
                "is_draft": "false",
                "is_reply": "true",
                "parent_post_id": str(pid),
            },
            headers=headers,
        )
        assert res.status_code == 200

    def test_add_post_with_image_upload(self, client):
        headers = setup_user(client, "uploader_api")
        image = io.BytesIO(b"fake image data")
        res = client.post(
            "/posts/add",
            data={
                "text": "Photo post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"image": ("test.jpg", image, "image/jpeg")},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["image_url"] is not None

    def test_add_post_with_video_upload(self, client):
        headers = setup_user(client, "vid_uploader")
        video = io.BytesIO(b"fake video data")
        res = client.post(
            "/posts/add",
            data={
                "text": "Video post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"video": ("clip.mp4", video, "video/mp4")},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["video_url"] is not None

    def test_add_post_with_audio_upload(self, client):
        headers = setup_user(client, "aud_uploader")
        audio = io.BytesIO(b"fake audio data")
        res = client.post(
            "/posts/add",
            data={
                "text": "Audio post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"audio": ("track.mp3", audio, "audio/mpeg")},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["audio_url"] is not None


class TestPublishDraftAPI:
    """POST /posts/drafts/publish/{id}."""

    def test_publish_response_schema(self, client):
        headers = setup_user(client, "pub_api")
        make_post(client, headers, text="Draft", is_draft="true")
        drafts = client.get("/posts/drafts", headers=headers).json()["drafts"]
        did = drafts[0]["id"]

        res = client.post(f"/posts/drafts/publish/{did}", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "published"
        assert body["post_id"] == did

    def test_publish_already_published_returns_400(self, client):
        headers = setup_user(client, "pub_twice")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/drafts/publish/{pid}", headers=headers)
        assert res.status_code == 400

    def test_publish_not_found(self, client):
        headers = setup_user(client, "pub_404")
        res = client.post("/posts/drafts/publish/99999", headers=headers)
        assert res.status_code == 404

    def test_publish_requires_auth(self, client):
        res = client.post("/posts/drafts/publish/1")
        assert res.status_code == 401
