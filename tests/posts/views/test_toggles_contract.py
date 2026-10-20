"""API contract tests for /posts toggle endpoints (like/laugh/repost/share/save/slop)."""

import pytest

from tests.helpers import make_post, setup_user


class TestPostsTogglesAPI:
    """Toggle endpoints: like, laugh, repost, share, save, slop."""

    # ── POST /posts/like/{id} ────────────────────────────────────────────

    def test_like_response_schema(self, client):
        headers = setup_user(client, "liker_api")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/like/{pid}", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "likes" in body
        assert "action" in body
        assert isinstance(body["likes"], int)
        assert body["action"] in ("liked", "unliked")

    def test_like_requires_auth(self, client):
        res = client.post("/posts/like/999")
        assert res.status_code == 401

    def test_like_not_found(self, client):
        headers = setup_user(client, "liker_404")
        res = client.post("/posts/like/99999", headers=headers)
        assert res.status_code == 404

    # ── POST /posts/laugh/{id} ───────────────────────────────────────────

    def test_laugh_response_schema(self, client):
        headers = setup_user(client, "laugher_api")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/laugh/{pid}", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "laughs" in body
        assert "action" in body
        assert isinstance(body["laughs"], int)
        assert body["action"] in ("laughed", "unlaughed")

    def test_laugh_requires_auth(self, client):
        res = client.post("/posts/laugh/999")
        assert res.status_code == 401

    def test_laugh_not_found(self, client):
        headers = setup_user(client, "laugher_404")
        res = client.post("/posts/laugh/99999", headers=headers)
        assert res.status_code == 404

    # ── POST /posts/repost/{id} ──────────────────────────────────────────

    def test_repost_response_schema(self, client):
        headers = setup_user(client, "reposter_api")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/repost/{pid}", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "reposts" in body
        assert "action" in body
        assert body["action"] in ("re-posted", "un-re-posted")

    def test_repost_requires_auth(self, client):
        res = client.post("/posts/repost/999")
        assert res.status_code == 401

    def test_repost_not_found(self, client):
        headers = setup_user(client, "repost_404")
        res = client.post("/posts/repost/99999", headers=headers)
        assert res.status_code == 404

    # ── POST /posts/share/{id} ───────────────────────────────────────────

    def test_share_response_schema(self, client):
        headers = setup_user(client, "sharer_api")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/share/{pid}", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "share_url" in body
        assert "shares" in body
        assert isinstance(body["shares"], int)
        assert body["share_url"].startswith("/post/")

    def test_share_anonymous_allowed(self, client):
        headers = setup_user(client, "share_anon")
        make_post(client, headers)
        pid = client.get("/posts/").json()["posts"][0]["id"]

        res = client.post(f"/posts/share/{pid}")
        assert res.status_code == 200
        assert res.json()["shares"] >= 1

    def test_share_not_found(self, client):
        res = client.post("/posts/share/99999")
        assert res.status_code == 404

    # ── POST /posts/save/{id} ────────────────────────────────────────────

    def test_save_response_schema(self, client):
        headers = setup_user(client, "saver_api")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/save/{pid}", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "saves" in body
        assert "action" in body
        assert body["action"] in ("saved", "unsaved")

    def test_save_requires_auth(self, client):
        res = client.post("/posts/save/999")
        assert res.status_code == 401

    def test_save_not_found(self, client):
        headers = setup_user(client, "save_404")
        res = client.post("/posts/save/99999", headers=headers)
        assert res.status_code == 404

    # ── Parametrized toggle auth / 404 ──────────────────────────────────

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/posts/like/999",
            "/posts/laugh/999",
            "/posts/repost/999",
            "/posts/save/999",
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_toggle_requires_auth(self, client, endpoint):
        res = client.post(endpoint)
        assert res.status_code == 401

    @pytest.mark.parametrize(
        "endpoint,username",
        [
            ("/posts/like/99999", "toggle_404_like"),
            ("/posts/laugh/99999", "toggle_404_laugh"),
            ("/posts/repost/99999", "toggle_404_repost"),
            ("/posts/save/99999", "toggle_404_save"),
        ],
        ids=["like", "laugh", "repost", "save"],
    )
    def test_toggle_not_found(self, client, endpoint, username):
        headers = setup_user(client, username)
        res = client.post(endpoint, headers=headers)
        assert res.status_code == 404

    # ── POST /posts/slop/{id} ────────────────────────────────────────────

    def test_slop_response_schema(self, client):
        headers = setup_user(client, "slop_api")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/slop/{pid}", json={"reason": "AI"}, headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "status" in body
        assert "post_id" in body
        assert body["status"] in ("ok", "updated")

    def test_slop_missing_reason_returns_400(self, client):
        headers = setup_user(client, "slop_noreason")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/slop/{pid}", json={}, headers=headers)
        assert res.status_code == 422
        assert res.status_code == 422

    def test_slop_non_string_reason_returns_400(self, client):
        headers = setup_user(client, "slop_badtype")
        make_post(client, headers)
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        res = client.post(f"/posts/slop/{pid}", json={"reason": None}, headers=headers)
        assert res.status_code == 422

    def test_slop_requires_auth(self, client):
        res = client.post("/posts/slop/999", json={"reason": "AI"})
        assert res.status_code == 401

    def test_slop_not_found(self, client):
        headers = setup_user(client, "slop_404")
        res = client.post("/posts/slop/99999", json={"reason": "AI"}, headers=headers)
        assert res.status_code == 404
