"""
Service-layer behavior tested through public API endpoints.
Rules: black-box only, real DB rows, no internal function mocking.
"""

import io
import json
import time


def _signup(client, username, password="password123"):
    return client.post(
        "/auth/signup",
        json={
            "username": username,
            "password": password,
            "email": f"{username}@test.com",
        },
    )


def _login(client, username, password="password123"):
    res = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _setup(client, username):
    _signup(client, username)
    return _login(client, username)


class TestMetadataThroughAPI:
    """get_metadata behavior tested through GET /posts/ response."""

    def test_valid_json_metadata_returned(self, client):
        h = _setup(client, "meta_api")
        client.post(
            "/posts/add",
            data={
                "text": "Post with metadata",
                "post_metadata": json.dumps({"tags": "python|rust", "location": "NYC"}),
                "is_draft": "false",
            },
            headers=h,
        )

        res = client.get("/posts/", headers=h)
        post = next(p for p in res.json()["posts"] if p["text"] == "Post with metadata")
        assert post["post_metadata"]["tags"] == ["python", "rust"]
        assert post["post_metadata"]["location"] == "NYC"

    def test_invalid_metadata_rejected(self, client):
        h = _setup(client, "meta_bad")
        res = client.post(
            "/posts/add",
            data={
                "text": "Bad metadata",
                "post_metadata": "{{not json",
                "is_draft": "false",
            },
            headers=h,
        )
        assert res.status_code == 400

    def test_empty_metadata_returns_empty_dict(self, client):
        h = _setup(client, "meta_empty")
        client.post(
            "/posts/add",
            data={
                "text": "No meta",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )

        res = client.get("/posts/", headers=h)
        post = next(p for p in res.json()["posts"] if p["text"] == "No meta")
        assert post["post_metadata"] == {}


class TestPostOrderingThroughAPI:
    """get_ordered_model behavior tested through feed endpoint ordering."""

    def test_posts_ordered_by_timestamp_desc(self, client):
        h = _setup(client, "order_api")
        client.post(
            "/posts/add",
            data={
                "text": "First post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )
        time.sleep(0.1)
        client.post(
            "/posts/add",
            data={
                "text": "Second post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )

        res = client.get("/posts/?limit=100", headers=h)
        posts = res.json()["posts"]
        my = [p for p in posts if p["username"] == "order_api"]
        assert len(my) >= 2
        # Most recent first
        assert my[0]["unix_timestamp"] >= my[1]["unix_timestamp"]


class TestQuotedPostThroughAPI:
    """build_quoted_post behavior tested through GET /posts/ response."""

    def test_quoted_post_data_in_response(self, client):
        h = _setup(client, "quote_api")
        # Create original
        client.post(
            "/posts/add",
            data={
                "text": "Original post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        # Quote it
        client.post(
            "/posts/add",
            data={
                "text": "My quote",
                "post_metadata": "{}",
                "is_draft": "false",
                "parent_post_id": str(pid),
            },
            headers=h,
        )

        res = client.get("/posts/?limit=100", headers=h)
        quote = next(p for p in res.json()["posts"] if p["text"] == "My quote")
        assert quote["quoted_post"] is not None
        assert quote["quoted_post"]["text"] == "Original post"
        assert quote["quoted_post"]["username"] == "quote_api"

    def test_no_quoted_post_when_no_parent(self, client):
        h = _setup(client, "noquote_api")
        client.post(
            "/posts/add",
            data={
                "text": "Standalone post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )

        res = client.get("/posts/", headers=h)
        post = next(p for p in res.json()["posts"] if p["text"] == "Standalone post")
        assert post["quoted_post"] is None


class TestBatchResponsesThroughAPI:
    """_build_post_responses behavior tested through feed interaction flags."""

    def test_liked_by_me_flag(self, client):
        h_a = _setup(client, "batch_a")
        h_b = _setup(client, "batch_b")

        client.post(
            "/posts/add",
            data={
                "text": "Batch test post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h_a,
        )
        pid = client.get("/posts/", headers=h_a).json()["posts"][0]["id"]

        # B likes it
        client.post(f"/posts/like/{pid}", headers=h_b)

        # B should see liked_by_me=True
        res = client.get("/posts/?limit=100", headers=h_b)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["liked_by_me"] is True

        # A should see liked_by_me=False
        res = client.get("/posts/?limit=100", headers=h_a)
        post = next(p for p in res.json()["posts"] if p["id"] == pid)
        assert post["liked_by_me"] is False

    def test_is_me_flag(self, client):
        h = _setup(client, "batch_me")
        client.post(
            "/posts/add",
            data={
                "text": "My own post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )

        res = client.get("/posts/?limit=100", headers=h)
        post = next(p for p in res.json()["posts"] if p["text"] == "My own post")
        assert post["is_me"] is True

    def test_anonymous_sees_default_flags(self, client):
        h = _setup(client, "batch_anon")
        client.post(
            "/posts/add",
            data={
                "text": "Anon visible",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )

        res = client.get("/posts/")
        post = next(p for p in res.json()["posts"] if p["text"] == "Anon visible")
        assert post["liked_by_me"] is False
        assert post["is_me"] is False


class TestDraftExclusionThroughAPI:
    """_exclude_drafts_query tested through feed responses."""

    def test_drafts_excluded_from_feed(self, client):
        h = _setup(client, "draft_excl")
        client.post(
            "/posts/add",
            data={
                "text": "Published post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h,
        )
        client.post(
            "/posts/add",
            data={
                "text": "Draft post",
                "post_metadata": "{}",
                "is_draft": "true",
            },
            headers=h,
        )

        res = client.get("/posts/?limit=100", headers=h)
        texts = [p["text"] for p in res.json()["posts"]]
        assert "Published post" in texts
        assert "Draft post" not in texts


class TestSlopExclusionThroughAPI:
    """_exclude_slopped_query tested through feed responses."""

    def test_slopped_posts_hidden_from_reporter(self, client):
        h_a = _setup(client, "slop_a")
        h_b = _setup(client, "slop_b")

        client.post(
            "/posts/add",
            data={
                "text": "Sloppy content",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            headers=h_a,
        )
        pid = client.get("/posts/", headers=h_a).json()["posts"][0]["id"]

        # B marks as slop
        client.post(f"/posts/slop/{pid}", json={"reason": "AI"}, headers=h_b)

        # B no longer sees it
        res = client.get("/posts/?limit=100", headers=h_b)
        assert not any(p["id"] == pid for p in res.json()["posts"])

        # A still sees it
        res = client.get("/posts/?limit=100", headers=h_a)
        assert any(p["id"] == pid for p in res.json()["posts"])


class TestMultimediaUploadThroughAPI:
    """get_multimedia_urls tested through POST /posts/add with files."""

    def test_image_upload_returns_url(self, client):
        h = _setup(client, "upload_img")
        img = io.BytesIO(b"\xff\xd8\xff\xe0")
        res = client.post(
            "/posts/add",
            data={
                "text": "Photo post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"image": ("photo.jpg", img, "image/jpeg")},
            headers=h,
        )
        assert res.status_code == 200
        assert res.json()["image_url"] is not None

    def test_video_upload_returns_url(self, client):
        h = _setup(client, "upload_vid")
        vid = io.BytesIO(b"\x00\x00\x00\x1cftyp")
        res = client.post(
            "/posts/add",
            data={
                "text": "Video post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"video": ("clip.mp4", vid, "video/mp4")},
            headers=h,
        )
        assert res.status_code == 200
        assert res.json()["video_url"] is not None

    def test_audio_upload_returns_url(self, client):
        h = _setup(client, "upload_aud")
        aud = io.BytesIO(b"\xff\xfb\x90\x00")
        res = client.post(
            "/posts/add",
            data={
                "text": "Audio post",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"audio": ("track.mp3", aud, "audio/mpeg")},
            headers=h,
        )
        assert res.status_code == 200
        assert res.json()["audio_url"] is not None

    def test_invalid_extension_rejected(self, client):
        h = _setup(client, "upload_bad")
        exe = io.BytesIO(b"MZ\x90\x00")
        res = client.post(
            "/posts/add",
            data={
                "text": "Bad file",
                "post_metadata": "{}",
                "is_draft": "false",
            },
            files={"image": ("mal.exe", exe, "application/octet-stream")},
            headers=h,
        )
        assert res.status_code == 200
        assert res.json()["image_url"] is None
