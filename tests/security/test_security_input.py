"""Security tests: input validation and sanitization."""

import json

import pytest

from tests.security._helpers import _make_post, _setup, _signup


class TestInputValidation:
    """Validate that the API properly sanitizes/rejects bad input."""

    # ── Username validation ──────────────────────────────────────────────

    def test_username_too_short(self, client):
        res = _signup(client, "ab", "password123")
        assert res.status_code == 400

    def test_username_too_long(self, client):
        res = _signup(client, "a" * 81, "password123")
        assert res.status_code == 400

    def test_username_empty_string(self, client):
        res = _signup(client, "", "password123")
        assert res.status_code == 400

    def test_password_too_short(self, client):
        res = _signup(client, "pw_test", "1234567")
        assert res.status_code == 400

    def test_password_empty_string(self, client):
        res = _signup(client, "pw_empty", "")
        assert res.status_code == 400

    # ── Post text validation ─────────────────────────────────────────────

    def test_post_text_exceeds_max_length(self, client):
        h = _setup(client, "longpost_sec")
        res = _make_post(client, h, text="x" * 5001)
        assert res.status_code == 400

    def test_post_text_at_max_length_accepted(self, client):
        h = _setup(client, "maxpost_sec")
        res = _make_post(client, h, text="x" * 5000)
        assert res.status_code == 200

    # ── Metadata injection ───────────────────────────────────────────────

    def test_invalid_json_metadata_rejected(self, client):
        h = _setup(client, "badmeta_sec")
        res = client.post(
            "/posts/add", data={"text": "Bad meta", "post_metadata": "{{not json"}, headers=h
        )
        assert res.status_code == 400

    def test_nested_object_in_metadata(self, client):
        h = _setup(client, "nested_meta")
        deep = json.dumps({"tags": "a|b", "nested": {"deep": {"deeper": "value"}}})
        res = client.post(
            "/posts/add",
            data={"text": "Deep meta", "post_metadata": deep, "is_draft": "false"},
            headers=h,
        )
        assert res.status_code == 200  # Accepted — stored as-is

    def test_huge_metadata_string(self, client):
        h = _setup(client, "huge_meta")
        big = json.dumps({"tags": "x" * 100000})
        res = client.post(
            "/posts/add",
            data={"text": "Big meta", "post_metadata": big, "is_draft": "false"},
            headers=h,
        )
        # Should either accept or reject gracefully (not 500)
        assert res.status_code in (200, 400, 413)

    # ── Slop reason validation ───────────────────────────────────────────

    def test_slop_missing_reason_key(self, client):
        h = _setup(client, "slop_noreason")
        _make_post(client, h)
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]
        res = client.post(f"/posts/slop/{pid}", json={}, headers=h)
        assert res.status_code == 422

    def test_slop_non_string_reason(self, client):
        """Pydantic v1 coerces int to str, so we test with None which violates the required field."""
        h = _setup(client, "slop_badtype")
        _make_post(client, h)
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]
        res = client.post(f"/posts/slop/{pid}", json={"reason": None}, headers=h)
        assert res.status_code == 422

    def test_slop_null_reason(self, client):
        h = _setup(client, "slop_null")
        _make_post(client, h)
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]
        res = client.post(f"/posts/slop/{pid}", json={"reason": None}, headers=h)
        assert res.status_code == 422

    # ── Nonexistent resource IDs ─────────────────────────────────────────

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/posts/like/999999",
            "/posts/repost/999999",
            "/posts/save/999999",
            "/posts/share/999999",
        ],
    )
    def test_nonexistent_post_returns_404(self, client, endpoint):
        h = _setup(client, f"nf_{endpoint.split('/')[-1]}")
        res = client.post(endpoint, headers=h)
        assert res.status_code == 404

    def test_publish_nonexistent_draft_returns_404(self, client):
        h = _setup(client, "pub_nf")
        res = client.post("/posts/drafts/publish/999999", headers=h)
        assert res.status_code == 404


class TestUsernameValidation:
    """Verify username character restrictions prevent S3 key injection."""

    @pytest.mark.parametrize(
        "username",
        [
            "../../evil",
            "has space",
            "<script>",
            'user"name',
            "user\x00name",
            "usеr",  # Cyrillic е
        ],
        ids=["slashes", "spaces", "html", "quotes", "null-byte", "unicode"],
    )
    def test_invalid_username_rejected(self, client, username):
        res = _signup(client, username, "password123")
        assert res.status_code == 400

    @pytest.mark.parametrize(
        "username",
        ["user.name-test_1", "TestUser123"],
        ids=["dots-dashes-underscores", "alphanumeric"],
    )
    def test_valid_username_accepted(self, client, username):
        res = _signup(client, username, "password123")
        assert res.status_code == 200


class TestXSSVectors:
    """Ensure XSS payloads in user input are stored as-is (not executed) and
    returned as JSON (not rendered as HTML)."""

    def test_xss_in_post_text_stored_safely(self, client):
        h = _setup(client, "xss_poster")
        xss = "<script>alert('xss')</script>"
        _make_post(client, h, text=xss)

        res = client.get("/posts/", headers=h)
        post = next(p for p in res.json()["posts"] if "<script>" in p["text"])
        # Returned as JSON string, not rendered HTML
        assert post["text"] == xss
        assert res.headers["content-type"] == "application/json"

    def test_xss_in_username_rejected_by_validation(self, client):
        xss_name = "<img onerror=alert(1) src=x>"
        res = _signup(client, xss_name, "password123")
        assert res.status_code == 400
        assert "letters, numbers" in res.json()["detail"]

    def test_xss_in_bio_stored_safely(self, client):
        h = _setup(client, "xss_bio")
        xss = "<img src=x onerror=alert(document.cookie)>"
        client.put("/profile/me", json={"bio": xss}, headers=h)

        res = client.get("/profile/xss_bio")
        assert res.json()["bio"] == xss
        assert res.headers["content-type"] == "application/json"

    def test_xss_in_metadata_tags(self, client):
        h = _setup(client, "xss_tags")
        meta = json.dumps({"tags": "<script>evil</script>|safe"})
        client.post(
            "/posts/add",
            data={"text": "Tagged xss", "post_metadata": meta, "is_draft": "false"},
            headers=h,
        )

        res = client.get("/posts/", headers=h)
        post = next(p for p in res.json()["posts"] if p["text"] == "Tagged xss")
        assert "<script>" in str(post["post_metadata"]["tags"])
        assert res.headers["content-type"] == "application/json"

    def test_xss_in_slop_reason(self, client):
        h = _setup(client, "xss_slop")
        _make_post(client, h)
        pid = client.get("/posts/", headers=h).json()["posts"][0]["id"]
        res = client.post(
            f"/posts/slop/{pid}", json={"reason": "<script>alert(1)</script>"}, headers=h
        )
        assert res.status_code == 200  # Stored safely, not executed
