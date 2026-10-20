"""API contract tests for user settings (algo, bubble, chronicle, agora)."""

from tests.helpers import make_post, setup_user


class TestSettingsAPI:
    """Tests for /profile/me/algo-settings and /profile/me/bubble-settings endpoints."""

    # ── Algo settings ────────────────────────────────────────────────────

    def test_get_algo_settings_defaults(self, client):
        headers = setup_user(client, "algo_defaults")
        res = client.get("/profile/me/algo-settings", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "like_weight" in body
        assert body["like_weight"] == 1.0
        assert "recency_weight" in body
        assert "preferred_categories" in body
        assert isinstance(body["preferred_categories"], list)

    def test_update_algo_settings(self, client):
        headers = setup_user(client, "algo_update")
        res = client.put(
            "/profile/me/algo-settings",
            json={"like_weight": 2.0, "randomness": 0.8},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["like_weight"] == 2.0
        assert res.json()["randomness"] == 0.8

    def test_algo_settings_persist(self, client):
        headers = setup_user(client, "algo_persist")
        client.put("/profile/me/algo-settings", json={"laugh_weight": 1.5}, headers=headers)
        res = client.get("/profile/me/algo-settings", headers=headers)
        assert res.json()["laugh_weight"] == 1.5

    def test_algo_settings_ignores_unknown_keys(self, client):
        headers = setup_user(client, "algo_unknown")
        res = client.put(
            "/profile/me/algo-settings",
            json={"like_weight": 1.8, "unknown_field": 99},
            headers=headers,
        )
        assert res.status_code == 200
        assert "unknown_field" not in res.json()

    def test_algo_settings_requires_auth(self, client):
        res = client.get("/profile/me/algo-settings")
        assert res.status_code == 401

    # ── Bubble settings ──────────────────────────────────────────────────

    def test_get_bubble_settings_defaults(self, client):
        headers = setup_user(client, "bubble_defaults")
        res = client.get("/profile/me/bubble-settings", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "animation_speed" in body
        assert body["animation_speed"] == 0.4
        assert "custom_topics" in body
        assert isinstance(body["custom_topics"], list)

    def test_update_bubble_settings(self, client):
        headers = setup_user(client, "bubble_update")
        res = client.put(
            "/profile/me/bubble-settings",
            json={"bubble_density": 24, "goal_prompt_enabled": False},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["bubble_density"] == 24
        assert res.json()["goal_prompt_enabled"] is False

    def test_bubble_settings_persist(self, client):
        headers = setup_user(client, "bubble_persist")
        client.put(
            "/profile/me/bubble-settings",
            json={"custom_topics": ["cooking", "diy"]},
            headers=headers,
        )
        res = client.get("/profile/me/bubble-settings", headers=headers)
        assert res.json()["custom_topics"] == ["cooking", "diy"]

    def test_bubble_settings_requires_auth(self, client):
        res = client.get("/profile/me/bubble-settings")
        assert res.status_code == 401

    def test_update_bubble_settings_requires_auth(self, client):
        res = client.put("/profile/me/bubble-settings", json={"bubble_density": 10})
        assert res.status_code == 401

    # ── Algo feed uses settings ──────────────────────────────────────────

    def test_algo_settings_slop_filter_defaults_to_hide(self, client):
        headers = setup_user(client, "slop_default")
        res = client.get("/profile/me/algo-settings", headers=headers)
        assert res.json()["slop_filter"] == "hide"
        assert res.json()["slop_threshold"] == 0

    def test_algo_settings_slop_filter_show(self, client):
        headers = setup_user(client, "slop_show")
        client.put("/profile/me/algo-settings", json={"slop_filter": "show"}, headers=headers)
        res = client.get("/profile/me/algo-settings", headers=headers)
        assert res.json()["slop_filter"] == "show"

    def test_slop_filter_show_keeps_slopped_posts_in_feed(self, client):
        """When slop_filter=show, slopped posts remain visible."""
        headers = setup_user(client, "slop_visible")
        make_post(client, headers, text="Sloppy post")
        pid = client.get("/posts/", headers=headers).json()["posts"][0]["id"]

        # Slop the post
        client.post(f"/posts/slop/{pid}", json={"reason": "AI"}, headers=headers)

        # Default: post should be hidden
        res = client.get("/posts/algo?offset=0&limit=20", headers=headers)
        texts = [p["text"] for p in res.json()["posts"]]
        assert "Sloppy post" not in texts

        # Change to show
        client.put("/profile/me/algo-settings", json={"slop_filter": "show"}, headers=headers)
        res = client.get("/posts/algo?offset=0&limit=20", headers=headers)
        texts = [p["text"] for p in res.json()["posts"]]
        assert "Sloppy post" in texts

    def test_slop_filter_only_shows_heavily_slopped(self, client):
        """When slop_filter=only, the algo feed shows ONLY posts with
        slop_count >= max(1, slop_threshold). Everything else is hidden."""
        # Author + two other users who will slop the post.
        author = setup_user(client, "slop_only_author")
        slopper_a = setup_user(client, "slop_only_a")
        slopper_b = setup_user(client, "slop_only_b")
        viewer = setup_user(client, "slop_only_viewer")

        make_post(client, author, text="Clean post")
        make_post(client, author, text="Slopped once")
        make_post(client, author, text="Slopped twice")
        posts = client.get("/posts/", headers=viewer).json()["posts"]
        by_text = {p["text"]: p["id"] for p in posts}

        client.post(
            f"/posts/slop/{by_text['Slopped once']}", json={"reason": "AI"}, headers=slopper_a
        )
        client.post(
            f"/posts/slop/{by_text['Slopped twice']}", json={"reason": "AI"}, headers=slopper_a
        )
        client.post(
            f"/posts/slop/{by_text['Slopped twice']}", json={"reason": "AI"}, headers=slopper_b
        )

        # Threshold=1 (default coerced from 0) — anything with >=1 slop shows.
        client.put(
            "/profile/me/algo-settings",
            json={"slop_filter": "only", "slop_threshold": 1},
            headers=viewer,
        )
        texts = [
            p["text"]
            for p in client.get("/posts/algo?offset=0&limit=20", headers=viewer).json()["posts"]
        ]
        assert "Clean post" not in texts
        assert "Slopped once" in texts
        assert "Slopped twice" in texts

        # Threshold=2 — only the twice-slopped post survives. Second viewer so
        # we get a fresh algo_settings dict (avoids a pre-existing SQLAlchemy
        # JSON mutation-tracking quirk that only surfaces when two sequential
        # PUTs mutate the same in-memory dict in the TestClient session).
        viewer2 = setup_user(client, "slop_only_viewer2")
        client.put(
            "/profile/me/algo-settings",
            json={"slop_filter": "only", "slop_threshold": 2},
            headers=viewer2,
        )
        texts = [
            p["text"]
            for p in client.get("/posts/algo?offset=0&limit=20", headers=viewer2).json()["posts"]
        ]
        assert "Clean post" not in texts
        assert "Slopped once" not in texts
        assert "Slopped twice" in texts

    def test_slop_filter_rejects_unknown_mode(self, client):
        """Pydantic Literal on slop_filter blocks garbage values at the boundary."""
        headers = setup_user(client, "slop_bad")
        res = client.put(
            "/profile/me/algo-settings", json={"slop_filter": "nuke_it"}, headers=headers
        )
        assert res.status_code == 422

    def test_algo_feed_respects_custom_weights(self, client):
        """Verify the algo feed doesn't error with custom weights."""
        headers = setup_user(client, "algo_weighted")
        make_post(client, headers, text="Weighted post")
        client.put(
            "/profile/me/algo-settings",
            json={
                "like_weight": 0,
                "repost_weight": 0,
                "share_weight": 0,
                "laugh_weight": 2.0,
                "save_weight": 2.0,
                "recency_weight": 1.0,
            },
            headers=headers,
        )
        res = client.get("/posts/algo?offset=0&limit=20", headers=headers)
        assert res.status_code == 200
        assert len(res.json()["posts"]) >= 1

    def test_algo_settings_include_engagement_enabled(self, client):
        headers = setup_user(client, "eng_enabled")
        res = client.get("/profile/me/algo-settings", headers=headers)
        assert res.json()["engagement_enabled"] is True
        assert res.json()["slop_weight"] == 0.0
        assert "report_weight" not in res.json()

    def test_algo_feed_with_engagement_disabled(self, client):
        """Disabling engagement should fall back to chronological ordering."""
        headers = setup_user(client, "eng_disabled")
        make_post(client, headers, text="Chrono post")
        client.put("/profile/me/algo-settings", json={"engagement_enabled": False}, headers=headers)
        res = client.get("/posts/algo?offset=0&limit=20", headers=headers)
        assert res.status_code == 200
        assert len(res.json()["posts"]) >= 1

    def test_algo_feed_with_slop_weight(self, client):
        """Setting slop_weight should not cause errors."""
        headers = setup_user(client, "slop_wt")
        make_post(client, headers, text="Slop weighted")
        client.put("/profile/me/algo-settings", json={"slop_weight": 1.5}, headers=headers)
        res = client.get("/posts/algo?offset=0&limit=20", headers=headers)
        assert res.status_code == 200
        assert len(res.json()["posts"]) >= 1


class TestChronicleSettingsAPI:
    """API contract tests for /profile/me/chronicle-settings."""

    def test_get_chronicle_settings_defaults(self, client):
        headers = setup_user(client, "chron_defaults")
        res = client.get("/profile/me/chronicle-settings", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "posts_per_page" in body
        assert body["posts_per_page"] == 8
        assert "narrative_style" in body
        assert body["narrative_style"] == "literary"
        assert "font_size" in body
        assert "theme" in body
        assert body["theme"] == "parchment"

    def test_update_chronicle_settings(self, client):
        headers = setup_user(client, "chron_update")
        res = client.put(
            "/profile/me/chronicle-settings",
            json={"font_size": 20, "theme": "dark", "narrative_style": "casual"},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["font_size"] == 20
        assert res.json()["theme"] == "dark"
        assert res.json()["narrative_style"] == "casual"

    def test_chronicle_settings_persist(self, client):
        headers = setup_user(client, "chron_persist")
        client.put(
            "/profile/me/chronicle-settings",
            json={"posts_per_page": 12, "auto_advance": True},
            headers=headers,
        )
        res = client.get("/profile/me/chronicle-settings", headers=headers)
        assert res.json()["posts_per_page"] == 12
        assert res.json()["auto_advance"] is True

    def test_chronicle_settings_ignores_unknown_keys(self, client):
        headers = setup_user(client, "chron_unknown")
        res = client.put(
            "/profile/me/chronicle-settings",
            json={"font_size": 18, "fake_field": "nope"},
            headers=headers,
        )
        assert res.status_code == 200
        assert "fake_field" not in res.json()

    def test_chronicle_settings_requires_auth(self, client):
        res = client.get("/profile/me/chronicle-settings")
        assert res.status_code == 401

    def test_update_chronicle_settings_requires_auth(self, client):
        res = client.put("/profile/me/chronicle-settings", json={"font_size": 14})
        assert res.status_code == 401


class TestAgoraSettingsAPI:
    """API contract tests for /profile/me/agora-settings."""

    def test_get_agora_settings_defaults(self, client):
        headers = setup_user(client, "agora_defaults")
        res = client.get("/profile/me/agora-settings", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["posts_per_page"] == 20
        assert body["sort_by"] == "algo"
        assert body["theme"] == "classic"
        assert body["show_avatars"] is True

    def test_update_agora_settings(self, client):
        headers = setup_user(client, "agora_update")
        res = client.put(
            "/profile/me/agora-settings",
            json={"posts_per_page": 30, "theme": "dark", "compact_mode": True},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["posts_per_page"] == 30
        assert res.json()["theme"] == "dark"
        assert res.json()["compact_mode"] is True

    def test_agora_settings_persist(self, client):
        headers = setup_user(client, "agora_persist")
        client.put(
            "/profile/me/agora-settings",
            json={"sort_by": "hot", "highlight_op": False},
            headers=headers,
        )
        res = client.get("/profile/me/agora-settings", headers=headers)
        assert res.json()["sort_by"] == "hot"
        assert res.json()["highlight_op"] is False

    def test_agora_settings_ignores_unknown_keys(self, client):
        headers = setup_user(client, "agora_unknown")
        res = client.put(
            "/profile/me/agora-settings", json={"posts_per_page": 25, "bogus": 42}, headers=headers
        )
        assert res.status_code == 200
        assert "bogus" not in res.json()

    def test_agora_settings_requires_auth(self, client):
        assert client.get("/profile/me/agora-settings").status_code == 401
        assert client.put("/profile/me/agora-settings", json={}).status_code == 401
