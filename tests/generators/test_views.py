"""Tests for generator admin-only REST endpoints."""

import pytest

from app.generators.constants import WEB_SCRAPING_UNAVAILABLE

RSS_SOURCE = {
    "name": "Test Source",
    "site_url": "https://example.com",
    "platform": "rss",
    "platform_config": {"feed_url": "https://example.com/feed.xml"},
}

# ── Helpers ─────────────────────────────────────────────────────────────


@pytest.fixture()
def admin_user(create_user):
    return create_user(username="admin", is_admin=True)


@pytest.fixture()
def admin_header(admin_user, auth_header):
    return auth_header("admin")


@pytest.fixture()
def regular_user(create_user):
    return create_user(username="regular", is_admin=False)


@pytest.fixture()
def regular_header(regular_user, auth_header):
    return auth_header("regular")


@pytest.fixture()
def source(admin_header, client):
    """Create a source via the API and return its dict."""
    resp = client.post("/generators/sources", json=RSS_SOURCE, headers=admin_header)
    assert resp.status_code == 200
    return resp.json()["source"]


# ── Non-admin access denied (403) ───────────────────────────────────────


class TestNonAdminBlocked:
    """All generator endpoints must return 403 for non-admin users."""

    ENDPOINTS = [
        ("GET", "/generators/sources"),
        ("POST", "/generators/sources"),
        ("GET", "/generators/sources/1"),
        ("PUT", "/generators/sources/1"),
        ("DELETE", "/generators/sources/1"),
        ("GET", "/generators/sources/1/profiles"),
        ("POST", "/generators/profiles"),
        ("DELETE", "/generators/profiles/1"),
        ("GET", "/generators/sources/1/runs"),
        ("POST", "/generators/run"),
        ("POST", "/generators/analyze"),
        ("POST", "/generators/sources/1/analyze"),
    ]

    @pytest.mark.parametrize(
        "method,path",
        ENDPOINTS,
        ids=[f"{m}-{p.split('/')[-1]}" for m, p in ENDPOINTS],
    )
    def test_non_admin_gets_403(self, method, path, client, regular_header):
        requester = getattr(client, method.lower())
        kwargs = {"headers": regular_header}
        if method in ("POST", "PUT"):
            kwargs["json"] = {
                "name": "x",
                "site_url": "https://x.com",
                "source_id": 1,
                "user_id": 1,
            }
        resp = requester(path, **kwargs)
        assert resp.status_code == 403


class TestUnauthenticatedBlocked:
    """Endpoints must reject requests without auth."""

    def test_list_sources_no_auth(self, client):
        resp = client.get("/generators/sources")
        assert resp.status_code == 401


# ── Sources CRUD ────────────────────────────────────────────────────────


class TestSourcesCRUD:
    def test_create_source(self, client, admin_header):
        resp = client.post(
            "/generators/sources",
            json={**RSS_SOURCE, "name": "New Source", "site_url": "https://news.example.com"},
            headers=admin_header,
        )
        assert resp.status_code == 200
        data = resp.json()["source"]
        assert data["name"] == "New Source"
        assert data["site_url"] == "https://news.example.com"
        assert data["is_active"] is True

    def test_list_sources(self, client, admin_header, source):
        resp = client.get("/generators/sources", headers=admin_header)
        assert resp.status_code == 200
        sources = resp.json()["sources"]
        assert len(sources) >= 1

    def test_get_source(self, client, admin_header, source):
        resp = client.get(f"/generators/sources/{source['id']}", headers=admin_header)
        assert resp.status_code == 200
        assert resp.json()["source"]["name"] == "Test Source"

    def test_get_source_not_found(self, client, admin_header):
        resp = client.get("/generators/sources/9999", headers=admin_header)
        assert resp.status_code == 404

    def test_update_source(self, client, admin_header, source):
        resp = client.put(
            f"/generators/sources/{source['id']}",
            json={"name": "Updated Name", "is_active": False},
            headers=admin_header,
        )
        assert resp.status_code == 200
        data = resp.json()["source"]
        assert data["name"] == "Updated Name"
        assert data["is_active"] is False

    def test_delete_source(self, client, admin_header, source):
        resp = client.delete(f"/generators/sources/{source['id']}", headers=admin_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone
        resp = client.get(f"/generators/sources/{source['id']}", headers=admin_header)
        assert resp.status_code == 404


# ── Profiles ────────────────────────────────────────────────────────────


class TestProfiles:
    def test_attach_profile(self, client, admin_header, source, create_user):
        bot = create_user(username="bot_user")
        resp = client.post(
            "/generators/profiles",
            json={"source_id": source["id"], "user_id": bot.id},
            headers=admin_header,
        )
        assert resp.status_code == 200
        profile = resp.json()["profile"]
        assert profile["source_id"] == source["id"]
        assert profile["user_id"] == bot.id
        assert profile["username"] == "bot_user"

    def test_attach_duplicate_profile_409(self, client, admin_header, source, create_user):
        bot = create_user(username="bot_user")
        client.post(
            "/generators/profiles",
            json={"source_id": source["id"], "user_id": bot.id},
            headers=admin_header,
        )
        resp = client.post(
            "/generators/profiles",
            json={"source_id": source["id"], "user_id": bot.id},
            headers=admin_header,
        )
        assert resp.status_code == 409

    def test_list_profiles(self, client, admin_header, source, create_user):
        bot = create_user(username="bot_user")
        client.post(
            "/generators/profiles",
            json={"source_id": source["id"], "user_id": bot.id},
            headers=admin_header,
        )
        resp = client.get(
            f"/generators/sources/{source['id']}/profiles",
            headers=admin_header,
        )
        assert resp.status_code == 200
        assert len(resp.json()["profiles"]) == 1

    def test_detach_profile(self, client, admin_header, source, create_user):
        bot = create_user(username="bot_user")
        attach_resp = client.post(
            "/generators/profiles",
            json={"source_id": source["id"], "user_id": bot.id},
            headers=admin_header,
        )
        profile_id = attach_resp.json()["profile"]["id"]

        resp = client.delete(f"/generators/profiles/{profile_id}", headers=admin_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "detached"

    def test_attach_nonexistent_user_404(self, client, admin_header, source):
        resp = client.post(
            "/generators/profiles",
            json={"source_id": source["id"], "user_id": 99999},
            headers=admin_header,
        )
        assert resp.status_code == 404


# ── Runs ────────────────────────────────────────────────────────────────


class TestRuns:
    def test_list_runs_empty(self, client, admin_header, source):
        resp = client.get(
            f"/generators/sources/{source['id']}/runs",
            headers=admin_header,
        )
        assert resp.status_code == 200
        assert resp.json()["runs"] == []


# ── Platforms (the public edition: RSS, no web scraper) ────────────────


class TestPlatformSources:
    def test_create_rss_source(self, client, admin_header):
        resp = client.post("/generators/sources", json=RSS_SOURCE, headers=admin_header)
        assert resp.status_code == 200
        data = resp.json()["source"]
        assert data["platform"] == "rss"
        assert data["platform_config"]["feed_url"] == "https://example.com/feed.xml"

    def test_create_rss_source_rejects_missing_feed_url(self, client, admin_header):
        resp = client.post(
            "/generators/sources",
            json={**RSS_SOURCE, "platform_config": {}},
            headers=admin_header,
        )
        assert resp.status_code == 422

    def test_create_with_unknown_platform_rejected(self, client, admin_header):
        resp = client.post(
            "/generators/sources",
            json={"name": "ms", "site_url": "https://myspace.com", "platform": "myspace"},
            headers=admin_header,
        )
        assert resp.status_code == 422

    def test_default_web_platform_unavailable(self, client, admin_header):
        resp = client.post(
            "/generators/sources",
            json={"name": "web src", "site_url": "https://example.com"},
            headers=admin_header,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == WEB_SCRAPING_UNAVAILABLE


# ── Analyze ─────────────────────────────────────────────────────────────


class TestAnalyze:
    def test_analyze_site_unavailable(self, client, admin_header):
        resp = client.post(
            "/generators/analyze",
            json={"site_url": "https://example.com", "content_hint": "memes"},
            headers=admin_header,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == WEB_SCRAPING_UNAVAILABLE

    def test_analyze_and_save_unavailable(self, client, admin_header, source):
        resp = client.post(f"/generators/sources/{source['id']}/analyze", headers=admin_header)
        assert resp.status_code == 422


class TestUpdatePlatform:
    def test_switching_to_an_unsupported_platform_is_rejected(self, client, admin_header, source):
        resp = client.put(
            f"/generators/sources/{source['id']}",
            json={"platform": "myspace"},
            headers=admin_header,
        )
        assert resp.status_code == 422

    def test_platform_names_must_look_like_identifiers(self, client, admin_header):
        resp = client.post(
            "/generators/sources",
            json={**RSS_SOURCE, "platform": "Not A Name"},
            headers=admin_header,
        )
        assert resp.status_code == 422
