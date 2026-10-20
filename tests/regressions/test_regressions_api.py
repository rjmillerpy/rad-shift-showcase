"""
Regression tests (part 2 of 2) — uploads, response shape, feed behaviour.

Covers bugs #10–#17 and post-numbering regressions.
"""

import io

from tests.regressions._helpers import _setup, _signup

# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #10: File uploads accepted any extension to S3
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression10FileExtensionAllowlist:
    def test_exe_not_uploaded(self, client):
        h = _setup(client, "ext_exe")
        exe = io.BytesIO(b"MZ\x90\x00")
        res = client.post(
            "/posts/add",
            data={"text": "EXE test", "post_metadata": "{}", "is_draft": "false"},
            files={"image": ("mal.exe", exe, "application/octet-stream")},
            headers=h,
        )
        assert res.json()["image_url"] is None

    def test_html_not_uploaded(self, client):
        h = _setup(client, "ext_html")
        html = io.BytesIO(b"<script>alert(1)</script>")
        res = client.post(
            "/posts/add",
            data={"text": "HTML test", "post_metadata": "{}", "is_draft": "false"},
            files={"image": ("page.html", html, "text/html")},
            headers=h,
        )
        assert res.json()["image_url"] is None

    def test_jpg_still_works(self, client):
        h = _setup(client, "ext_jpg")
        jpg = io.BytesIO(b"\xff\xd8\xff\xe0")
        res = client.post(
            "/posts/add",
            data={"text": "JPG test", "post_metadata": "{}", "is_draft": "false"},
            files={"image": ("photo.jpg", jpg, "image/jpeg")},
            headers=h,
        )
        assert res.json()["image_url"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #11: Client-supplied content_type passed directly to S3
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression11ContentTypeSpoofing:
    def test_spoofed_content_type_ignored(self, client):
        """Upload .jpg with text/html content_type — should still succeed
        because extension is valid, and the server-derived content_type is used."""
        h = _setup(client, "ct_spoof_reg")
        jpg = io.BytesIO(b"\xff\xd8\xff\xe0")
        res = client.post(
            "/posts/add",
            data={"text": "CT spoof", "post_metadata": "{}", "is_draft": "false"},
            files={"image": ("photo.jpg", jpg, "text/html")},
            headers=h,
        )
        assert res.status_code == 200
        assert res.json()["image_url"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #12: Username allowed special chars → S3 key path traversal
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression12UsernameSanitization:
    def test_slash_in_username_rejected(self, client):
        res = _signup(client, "../../admin")
        assert res.status_code == 400

    def test_angle_brackets_rejected(self, client):
        res = _signup(client, "<script>")
        assert res.status_code == 400

    def test_s3_key_sanitizer_strips_slashes(self):
        from app.posts.uploads import _sanitize_s3_key_part

        result = _sanitize_s3_key_part("user/../../etc")
        assert "/" not in result

    def test_s3_key_sanitizer_preserves_safe_chars(self):
        from app.posts.uploads import _sanitize_s3_key_part

        assert _sanitize_s3_key_part("normal_user.1") == "normal_user.1"
        assert _sanitize_s3_key_part("my-user") == "my-user"


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #15: Profile picture upload accepted non-image files
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression15ProfilePicValidation:
    def test_txt_file_rejected_for_profile_pic(self, client):
        h = _setup(client, "pic_txt")
        txt = io.BytesIO(b"not an image")
        res = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("doc.txt", txt, "text/plain")},
            headers=h,
        )
        assert res.status_code == 500
        assert "not allowed" in res.json()["detail"].lower()

    def test_png_accepted_for_profile_pic(self, client):
        h = _setup(client, "pic_png_reg")
        png = io.BytesIO(b"\x89PNG\r\n\x1a\n")
        res = client.post(
            "/profile/me/upload-profile-pic",
            files={"file": ("avatar.png", png, "image/png")},
            headers=h,
        )
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG #17: Reply/quote/slop buttons had no counters
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegression17CountersInResponse:
    def test_replies_count_in_feed(self, client):
        h = _setup(client, "count_replies")
        client.post(
            "/posts/add",
            data={"text": "Parent", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        # Add reply
        client.post(
            "/posts/add",
            data={
                "text": "Reply",
                "post_metadata": "{}",
                "is_draft": "false",
                "is_reply": "true",
                "parent_post_id": str(pid),
            },
            headers=h,
        )

        post = next(p for p in client.get("/posts/", headers=h).json()["posts"] if p["id"] == pid)
        assert post["replies_count"] == 1

    def test_quotes_count_in_feed(self, client):
        h = _setup(client, "count_quotes")
        client.post(
            "/posts/add",
            data={"text": "Quotable", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        # Quote post (parent_post_id without is_reply)
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

        post = next(p for p in client.get("/posts/", headers=h).json()["posts"] if p["id"] == pid)
        assert post["quotes_count"] == 1

    def test_slop_count_in_feed(self, client):
        h = _setup(client, "count_slop")
        client.post(
            "/posts/add",
            data={"text": "Sloppy", "post_metadata": "{}", "is_draft": "false"},
            headers=h,
        )
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]

        client.post(f"/posts/slop/{pid}", json={"reason": "AI"}, headers=h)

        # Need a different user to see the count (original user has it slopped)
        h2 = _setup(client, "count_viewer")
        post = next(p for p in client.get("/posts/", headers=h2).json()["posts"] if p["id"] == pid)
        assert post["slop_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG: share_post returned /posts/{id} instead of /post/{id}
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegressionShareURL:
    def test_share_url_uses_singular_post(self, client, create_user, create_post, auth_header):
        user = create_user(username="share_url_user")
        post = create_post(user=user, text="Share URL test")
        res = client.post(f"/posts/share/{post.id}", headers=auth_header("share_url_user"))
        assert res.status_code == 200
        url = res.json()["share_url"]
        assert url.startswith("/post/")
        assert not url.startswith("/posts/")


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG: Profile API returned 'timestamp' key instead of 'unix_timestamp'
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegressionProfileTimestamp:
    def test_profile_posts_use_unix_timestamp(self, client, create_user, create_post, auth_header):
        user = create_user(username="ts_user")
        create_post(user=user, text="Timestamp test")
        res = client.get("/profile/ts_user")
        assert res.status_code == 200
        post = res.json()["posts"][0]
        assert "unix_timestamp" in post
        assert "timestamp" not in post
        assert isinstance(post["unix_timestamp"], int)


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG: Laugh reaction not in PostResponse
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegressionLaughInResponse:
    def test_feed_includes_laughs_and_laughed_by_me(
        self, client, create_user, create_post, auth_header
    ):
        user = create_user(username="laugh_resp")
        post = create_post(user=user, text="Laugh response test")
        client.post(f"/posts/laugh/{post.id}", headers=auth_header("laugh_resp"))

        res = client.get("/posts/", headers=auth_header("laugh_resp"))
        feed_post = res.json()["posts"][0]
        assert "laughs" in feed_post
        assert feed_post["laughs"] == 1
        assert "laughed_by_me" in feed_post
        assert feed_post["laughed_by_me"] is True


# ═══════════════════════════════════════════════════════════════════════════════
#  BUG: Slop filter setting not respected by algo feed
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegressionSlopFilterSetting:
    def test_slop_filter_show_keeps_posts(self, client, create_user, create_post, auth_header):
        user = create_user(username="slop_filter_user")
        post = create_post(user=user, text="Sloppable post")
        h = auth_header("slop_filter_user")

        # Slop it
        client.post(f"/posts/slop/{post.id}", json={"reason": "test"}, headers=h)

        # Default: hidden
        res = client.get("/posts/algo", headers=h)
        assert all(p["text"] != "Sloppable post" for p in res.json()["posts"])

        # Set filter to show
        client.put("/profile/me/algo-settings", json={"slop_filter": "show"}, headers=h)
        res = client.get("/posts/algo", headers=h)
        assert any(p["text"] == "Sloppable post" for p in res.json()["posts"])
