"""Security tests: IDOR — users cannot access others' resources."""

from tests.security._helpers import _make_post, _setup


class TestIDOR:
    """Insecure direct object reference: user A cannot act on user B's private data."""

    def test_cannot_publish_another_users_draft(self, client):
        h_a = _setup(client, "idor_a")
        h_b = _setup(client, "idor_b")

        _make_post(client, h_a, text="A's draft", is_draft=True)
        drafts = client.get("/posts/drafts", headers=h_a).json()["drafts"]
        draft_id = drafts[0]["id"]

        # User B tries to publish A's draft
        res = client.post(f"/posts/drafts/publish/{draft_id}", headers=h_b)
        assert res.status_code == 404, "User B should not be able to publish user A's draft"

    def test_cannot_see_another_users_drafts(self, client):
        h_a = _setup(client, "draft_a")
        h_b = _setup(client, "draft_b")

        _make_post(client, h_a, text="A's secret draft", is_draft=True)

        # User B's drafts should not include A's draft
        drafts = client.get("/posts/drafts", headers=h_b).json()["drafts"]
        assert not any(d["text"] == "A's secret draft" for d in drafts)

    def test_drafts_hidden_from_public_feed(self, client):
        h = _setup(client, "draft_hidden")
        _make_post(client, h, text="Hidden draft", is_draft=True)

        # Not in public feed
        posts = client.get("/posts/").json()["posts"]
        assert not any(p["text"] == "Hidden draft" for p in posts)

        # Not in authenticated feed for another user
        h_other = _setup(client, "draft_viewer")
        posts = client.get("/posts/", headers=h_other).json()["posts"]
        assert not any(p["text"] == "Hidden draft" for p in posts)

    def test_cannot_see_another_users_saved_posts(self, client):
        h_a = _setup(client, "saved_a")
        h_b = _setup(client, "saved_b")

        _make_post(client, h_a, text="A's post")
        pid = client.get("/posts/", headers=h_a).json()["posts"][0]["id"]
        client.post(f"/posts/save/{pid}", headers=h_a)

        # User B's saved list should not contain A's saved post
        saved = client.get("/posts/saved", headers=h_b).json()["posts"]
        assert len(saved) == 0

    def test_slop_only_affects_reporting_user(self, client):
        h_a = _setup(client, "slop_a")
        h_b = _setup(client, "slop_b")

        _make_post(client, h_a, text="Slop target")
        pid = client.get("/posts/", headers=h_a).json()["posts"][0]["id"]

        # B marks as slop
        client.post(f"/posts/slop/{pid}", json={"reason": "AI"}, headers=h_b)

        # B doesn't see it
        b_posts = client.get("/posts/", headers=h_b).json()["posts"]
        assert not any(p["id"] == pid for p in b_posts)

        # A still sees it
        a_posts = client.get("/posts/", headers=h_a).json()["posts"]
        assert any(p["id"] == pid for p in a_posts)
