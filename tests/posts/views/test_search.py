"""API contract tests for /posts/search endpoints (posts and users)."""

from tests.helpers import make_post, setup_user


class TestSearchAPI:
    """GET /posts/search/posts, GET /posts/search/users"""

    def test_search_posts_response_schema(self, client):
        h = setup_user(client, "search_poster")
        make_post(client, h, text="Searchable content here")
        res = client.get("/posts/search/posts?q=Searchable")
        assert res.status_code == 200
        body = res.json()
        assert "posts" in body
        assert "has_more" in body
        assert len(body["posts"]) == 1
        assert "Searchable" in body["posts"][0]["text"]

    def test_search_posts_case_insensitive(self, client):
        h = setup_user(client, "search_case")
        make_post(client, h, text="UPPERCASE content")
        res = client.get("/posts/search/posts?q=uppercase")
        assert len(res.json()["posts"]) == 1

    def test_search_posts_partial_match(self, client):
        h = setup_user(client, "search_partial")
        make_post(client, h, text="This is a unique findable post")
        res = client.get("/posts/search/posts?q=findable")
        assert len(res.json()["posts"]) == 1

    def test_search_posts_no_results(self, client):
        res = client.get("/posts/search/posts?q=zzzznonexistent999")
        assert res.status_code == 200
        assert len(res.json()["posts"]) == 0

    def test_search_posts_empty_query(self, client):
        res = client.get("/posts/search/posts?q=")
        assert res.status_code == 200
        assert res.json()["posts"] == []

    def test_search_posts_excludes_drafts(self, client):
        h = setup_user(client, "search_draft")
        make_post(client, h, text="Draft searchable", is_draft="true")
        make_post(client, h, text="Published searchable")
        res = client.get("/posts/search/posts?q=searchable")
        texts = [p["text"] for p in res.json()["posts"]]
        assert "Published searchable" in texts
        assert "Draft searchable" not in texts

    def test_search_posts_pagination(self, client):
        h = setup_user(client, "search_pag")
        for i in range(5):
            make_post(client, h, text=f"Paginated search {i}")
        res = client.get("/posts/search/posts?q=Paginated&limit=3")
        assert len(res.json()["posts"]) == 3
        assert res.json()["has_more"] is True

    def test_search_posts_anonymous(self, client):
        h = setup_user(client, "search_anon")
        make_post(client, h, text="Anonymous searchable")
        res = client.get("/posts/search/posts?q=Anonymous")
        assert res.status_code == 200
        assert len(res.json()["posts"]) == 1

    def test_search_users_response_schema(self, client):
        setup_user(client, "searchable_user")
        res = client.get("/posts/search/users?q=searchable")
        assert res.status_code == 200
        body = res.json()
        assert "users" in body
        assert "has_more" in body
        assert len(body["users"]) >= 1
        user = body["users"][0]
        assert "username" in user
        assert "bio" in user
        assert "profile_picture_url" in user

    def test_search_users_no_results(self, client):
        res = client.get("/posts/search/users?q=zzzznonexistent999")
        assert res.json()["users"] == []

    def test_search_users_empty_query(self, client):
        res = client.get("/posts/search/users?q=")
        assert res.json()["users"] == []

    def test_search_users_case_insensitive(self, client):
        setup_user(client, "CamelCaseUser")
        res = client.get("/posts/search/users?q=camelcase")
        assert len(res.json()["users"]) >= 1

    def test_search_users_pagination(self, client):
        for i in range(5):
            setup_user(client, f"paguser_{i}")
        res = client.get("/posts/search/users?q=paguser&limit=3")
        assert len(res.json()["users"]) == 3
        assert res.json()["has_more"] is True
