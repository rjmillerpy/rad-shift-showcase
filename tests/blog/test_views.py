"""API-level tests for app/blog/views.py — full HTTP round-trip."""

import pytest

from app.blog.constants import (
    MAX_LIST_LIMIT,
    MAX_READ_TIME_SECONDS,
    MAX_TITLE_LEN,
    MAX_USERNAME_FILTER_LEN,
    AdPlacement,
)


def _create_blog(client, headers, title="My Post", content="<p>Some content here</p>", **kwargs):
    payload = {"title": title, "content_html": content, **kwargs}
    return client.post("/blog/create", json=payload, headers=headers)


class TestCreateBlog:
    def test_create_success(self, client, create_user, auth_header):
        create_user("blogger")
        resp = _create_blog(client, auth_header("blogger"))
        assert resp.status_code == 200
        post = resp.json()["blog_post"]
        assert post["title"] == "My Post"
        assert post["slug"] is not None
        assert post["is_draft"] is True

    def test_create_published(self, client, create_user, auth_header):
        create_user("blogger")
        resp = _create_blog(client, auth_header("blogger"), is_draft=False)
        post = resp.json()["blog_post"]
        assert post["is_published"] is True
        assert post["published_at"] is not None

    def test_create_requires_auth(self, client):
        resp = client.post("/blog/create", json={"title": "T", "content_html": "<p>x</p>"})
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        "payload",
        [
            {"content_html": "<p>body</p>"},
            {"title": "T"},
            {"title": "", "content_html": "<p>x</p>"},
            {"title": "T", "content_html": ""},
            {"title": "x" * (MAX_TITLE_LEN + 1), "content_html": "<p>x</p>"},
        ],
        ids=[
            "missing_title",
            "missing_content",
            "empty_title",
            "empty_content",
            "too_long_title",
        ],
    )
    def test_create_validation(self, client, create_user, auth_header, payload):
        create_user("blogger")
        resp = client.post("/blog/create", json=payload, headers=auth_header("blogger"))
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "placement,expected_stored",
        [
            (AdPlacement.NONE.value, AdPlacement.NONE.value),
            (AdPlacement.MINIMAL.value, AdPlacement.MINIMAL.value),
            (AdPlacement.STANDARD.value, AdPlacement.STANDARD.value),
        ],
        ids=list(AdPlacement),
    )
    def test_ad_placement_when_monetized(
        self,
        client,
        create_user,
        auth_header,
        placement,
        expected_stored,
    ):
        create_user("blogger")
        resp = _create_blog(
            client,
            auth_header("blogger"),
            monetized=True,
            ad_placement=placement,
        )
        assert resp.status_code == 200
        assert resp.json()["blog_post"]["ad_placement"] == expected_stored

    def test_ad_placement_invalid_rejected(self, client, create_user, auth_header):
        create_user("blogger")
        resp = _create_blog(
            client,
            auth_header("blogger"),
            monetized=True,
            ad_placement="premium",
        )
        assert resp.status_code == 422


class TestUpdateBlog:
    def test_update_title(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        post_id = _create_blog(client, headers).json()["blog_post"]["id"]
        resp = client.put(f"/blog/{post_id}", json={"title": "Updated"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["blog_post"]["title"] == "Updated"

    def test_update_content_regenerates_reading_time(
        self,
        client,
        create_user,
        auth_header,
    ):
        create_user("blogger")
        headers = auth_header("blogger")
        post = _create_blog(client, headers).json()["blog_post"]
        long_body = "<p>" + " ".join(["word"] * 800) + "</p>"
        resp = client.put(
            f"/blog/{post['id']}",
            json={"content_html": long_body},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["blog_post"]["reading_time_minutes"] > post["reading_time_minutes"]

    def test_update_nonexistent_404(self, client, create_user, auth_header):
        create_user("blogger")
        resp = client.put(
            "/blog/99999",
            json={"title": "No"},
            headers=auth_header("blogger"),
        )
        assert resp.status_code == 404

    def test_update_other_user_forbidden(self, client, create_user, auth_header):
        create_user("owner")
        create_user("intruder")
        post_id = _create_blog(client, auth_header("owner")).json()["blog_post"]["id"]
        resp = client.put(
            f"/blog/{post_id}",
            json={"title": "Hacked"},
            headers=auth_header("intruder"),
        )
        assert resp.status_code == 403


class TestPublishBlog:
    def test_publish_draft(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        post_id = _create_blog(client, headers, is_draft=True).json()["blog_post"]["id"]
        resp = client.post(f"/blog/{post_id}/publish", headers=headers)
        assert resp.status_code == 200
        post = resp.json()["blog_post"]
        assert post["is_published"] is True
        assert post["is_draft"] is False

    def test_publish_nonexistent_404(self, client, create_user, auth_header):
        create_user("blogger")
        resp = client.post("/blog/99999/publish", headers=auth_header("blogger"))
        assert resp.status_code == 404

    def test_publish_other_user_forbidden(self, client, create_user, auth_header):
        create_user("owner")
        create_user("intruder")
        post_id = _create_blog(client, auth_header("owner")).json()["blog_post"]["id"]
        resp = client.post(f"/blog/{post_id}/publish", headers=auth_header("intruder"))
        assert resp.status_code == 403


class TestOpenGraphFields:
    def test_og_defaults_derived_from_title_and_content(
        self,
        client,
        create_user,
        auth_header,
    ):
        create_user("og_default")
        resp = _create_blog(
            client,
            auth_header("og_default"),
            title="OG Default Title",
            content="<p>Body text that should feed the OG description.</p>",
        )
        post = resp.json()["blog_post"]
        assert post["og_title"] == "OG Default Title"
        assert "Body text" in post["og_description"]

    def test_og_defaults_to_featured_image(self, client, create_user, auth_header):
        create_user("og_featured")
        resp = _create_blog(
            client,
            auth_header("og_featured"),
            featured_image_url="https://example.com/img.png",
        )
        post = resp.json()["blog_post"]
        assert post["og_image"] == "https://example.com/img.png"

    def test_explicit_og_fields_preserved_through_update(
        self,
        client,
        create_user,
        auth_header,
    ):
        create_user("og_update")
        headers = auth_header("og_update")
        post_id = _create_blog(client, headers).json()["blog_post"]["id"]
        resp = client.put(
            f"/blog/{post_id}",
            json={
                "og_title": "Custom OG",
                "og_description": "Custom OG desc",
                "og_image": "https://example.com/custom.png",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        post = resp.json()["blog_post"]
        assert post["og_title"] == "Custom OG"
        assert post["og_description"] == "Custom OG desc"
        assert post["og_image"] == "https://example.com/custom.png"


class TestListBlogs:
    def test_list_returns_posts_and_has_more(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        for i in range(2):
            _create_blog(client, headers, title=f"P{i}", is_draft=False)
        resp = client.get("/blog/list")
        body = resp.json()
        assert len(body["posts"]) == 2
        assert body["has_more"] is False

    def test_list_pagination_has_more(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        for i in range(3):
            _create_blog(client, headers, title=f"P{i}", is_draft=False)
        resp = client.get("/blog/list?limit=2")
        body = resp.json()
        assert len(body["posts"]) == 2
        assert body["has_more"] is True

    def test_list_excludes_drafts(self, client, create_user, auth_header):
        create_user("blogger")
        _create_blog(client, auth_header("blogger"), title="Draft", is_draft=True)
        resp = client.get("/blog/list")
        assert resp.json()["posts"] == []

    def test_list_user_filter(self, client, create_user, auth_header):
        create_user("a")
        create_user("b")
        _create_blog(client, auth_header("a"), title="a-post", is_draft=False)
        _create_blog(client, auth_header("b"), title="b-post", is_draft=False)
        resp = client.get("/blog/list?user=a")
        titles = [p["title"] for p in resp.json()["posts"]]
        assert titles == ["a-post"]

    @pytest.mark.parametrize(
        "query",
        [
            f"limit={MAX_LIST_LIMIT + 1}",
            "limit=0",
            "offset=-1",
            f"user={'x' * (MAX_USERNAME_FILTER_LEN + 1)}",
        ],
        ids=["limit_too_high", "limit_zero", "offset_negative", "user_too_long"],
    )
    def test_list_rejects_invalid_paging(self, client, query):
        resp = client.get(f"/blog/list?{query}")
        assert resp.status_code == 422


class TestMyDrafts:
    def test_requires_auth(self, client):
        assert client.get("/blog/my-drafts").status_code == 401

    def test_returns_only_drafts(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        _create_blog(client, headers, title="Draft", is_draft=True)
        _create_blog(client, headers, title="Live", is_draft=False)
        resp = client.get("/blog/my-drafts", headers=headers)
        drafts = resp.json()["drafts"]
        assert len(drafts) == 1
        assert drafts[0]["title"] == "Draft"


class TestGetBySlug:
    def test_found(self, client, create_user, auth_header):
        create_user("blogger")
        post = _create_blog(
            client,
            auth_header("blogger"),
            title="Hello World",
        ).json()["blog_post"]
        resp = client.get(f"/blog/slug/{post['slug']}")
        assert resp.status_code == 200
        assert resp.json()["blog_post"]["title"] == "Hello World"

    def test_not_found_404(self, client):
        assert client.get("/blog/slug/nonexistent").status_code == 404


class TestTrackView:
    def test_success(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        post_id = _create_blog(client, headers, is_draft=False).json()["blog_post"]["id"]
        resp = client.post(f"/blog/{post_id}/view", json={"read_time_seconds": 30})
        assert resp.status_code == 200
        assert resp.json()["status"] == "recorded"

    def test_increments_count(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        post = _create_blog(client, headers, is_draft=False).json()["blog_post"]
        client.post(f"/blog/{post['id']}/view")
        client.post(f"/blog/{post['id']}/view")
        resp = client.get(f"/blog/slug/{post['slug']}")
        assert resp.json()["blog_post"]["view_count"] == 2

    def test_authenticated_view_records_user_id(
        self,
        client,
        create_user,
        auth_header,
        db_session,
    ):
        create_user("author_view")
        reader = create_user("reader_view")
        post_id = _create_blog(
            client,
            auth_header("author_view"),
            is_draft=False,
        ).json()["blog_post"]["id"]

        client.post(
            f"/blog/{post_id}/view",
            json={"read_time_seconds": 10},
            headers=auth_header("reader_view"),
        )
        from app.blog.models import BlogView

        row = db_session.query(BlogView).filter_by(blog_post_id=post_id).first()
        assert row.user_id == reader.id

    def test_nonexistent_404(self, client):
        assert client.post("/blog/99999/view").status_code == 404

    @pytest.mark.parametrize(
        "value",
        [-1, MAX_READ_TIME_SECONDS + 1, 10 * MAX_READ_TIME_SECONDS],
        ids=["negative", "over_cap", "way_over_cap"],
    )
    def test_read_time_bounds_enforced(self, client, create_user, auth_header, value):
        create_user("blogger")
        headers = auth_header("blogger")
        post_id = _create_blog(client, headers, is_draft=False).json()["blog_post"]["id"]
        resp = client.post(f"/blog/{post_id}/view", json={"read_time_seconds": value})
        assert resp.status_code == 422


class TestBlogStats:
    def test_get_stats(self, client, create_user, auth_header):
        create_user("blogger")
        headers = auth_header("blogger")
        post_id = _create_blog(client, headers, is_draft=False).json()["blog_post"]["id"]
        client.post(f"/blog/{post_id}/view", json={"read_time_seconds": 10})
        client.post(f"/blog/{post_id}/view", json={"read_time_seconds": 20})
        resp = client.get(f"/blog/{post_id}/stats", headers=headers)
        stats = resp.json()
        assert stats["view_count"] == 2
        assert stats["total_read_time_seconds"] == 30

    def test_requires_auth(self, client, create_user, auth_header):
        create_user("blogger")
        post_id = _create_blog(
            client,
            auth_header("blogger"),
        ).json()["blog_post"]["id"]
        assert client.get(f"/blog/{post_id}/stats").status_code == 401

    def test_forbidden_for_non_owner(self, client, create_user, auth_header):
        create_user("owner")
        create_user("other")
        post_id = _create_blog(
            client,
            auth_header("owner"),
        ).json()["blog_post"]["id"]
        resp = client.get(f"/blog/{post_id}/stats", headers=auth_header("other"))
        assert resp.status_code == 403
