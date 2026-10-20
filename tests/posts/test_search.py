"""Unit tests for app/posts/search.py."""

import json

from app.posts import search


class TestSearchPostsFormatted:
    def test_returns_matching_by_text(self, create_user, create_post, db_session):
        user = create_user(username="s_text")
        create_post(user=user, text="Findable phrase inside")
        create_post(user=user, text="Something else entirely")
        posts, _ = search.search_posts_formatted("Findable", db_session)
        assert len(posts) == 1
        assert "Findable" in posts[0].text

    def test_case_insensitive(self, create_user, create_post, db_session):
        user = create_user(username="s_case")
        create_post(user=user, text="MixedCase HIT")
        posts, _ = search.search_posts_formatted("mixedcase", db_session)
        assert len(posts) == 1

    def test_matches_metadata_tags(self, create_user, create_post, db_session):
        user = create_user(username="s_tag")
        create_post(user=user, text="body only", metadata={"tags": ["gardening"]})
        posts, _ = search.search_posts_formatted("gardening", db_session)
        assert len(posts) == 1

    def test_empty_query_falls_through_to_pattern(self, create_user, create_post, db_session):
        # `search_posts_formatted` doesn't guard the empty query — the caller
        # does. We just confirm it doesn't crash.
        user = create_user(username="s_empty")
        create_post(user=user, text="anything")
        posts, _ = search.search_posts_formatted("", db_session)
        assert len(posts) >= 1


class TestSearchUsers:
    def test_returns_matching_users(self, create_user, db_session):
        create_user(username="alice_findme")
        create_user(username="bob_skip")
        users, _ = search.search_users("findme", db_session)
        assert {u["username"] for u in users} == {"alice_findme"}

    def test_returned_fields(self, create_user, db_session):
        create_user(username="shape_check")
        users, _ = search.search_users("shape", db_session)
        row = users[0]
        assert set(row.keys()) == {"username", "bio", "profile_picture_url"}


class TestGetFeedTags:
    def _post_with_tags(self, user, create_post, tags):
        return create_post(user=user, text="body", metadata={"tags": tags})

    def test_empty_when_no_posts(self, db_session):
        assert search.get_feed_tags(db_session) == []

    def test_extracts_list_style_tags(self, create_user, create_post, db_session):
        user = create_user(username="tag_list")
        self._post_with_tags(user, create_post, ["python", "gardening"])
        tags = search.get_feed_tags(db_session, feed="main")
        assert "python" in tags and "gardening" in tags

    def test_extracts_pipe_string_tags(self, create_user, create_post, db_session):
        user = create_user(username="tag_pipe")
        self._post_with_tags(user, create_post, "one|two|three")
        tags = search.get_feed_tags(db_session, feed="main")
        assert {"one", "two", "three"} <= set(tags)

    def test_deduplicates_across_posts(self, create_user, create_post, db_session):
        user = create_user(username="tag_dedupe")
        self._post_with_tags(user, create_post, ["python"])
        self._post_with_tags(user, create_post, ["python"])
        tags = search.get_feed_tags(db_session, feed="main")
        assert tags.count("python") == 1

    def test_limit_capped(self, create_user, create_post, db_session):
        user = create_user(username="tag_limit")
        self._post_with_tags(user, create_post, [f"tag_{i}" for i in range(20)])
        tags = search.get_feed_tags(db_session, feed="main", limit=5)
        assert len(tags) == 5


class TestGetFullMetadata:
    def test_returns_none_for_bad_json(self, db_session):
        assert search.get_full_metadata("{not json", db_session) is None

    def test_splits_string_tags(self, db_session):
        result = search.get_full_metadata(json.dumps({"tags": "a|b|c"}), db_session)
        assert json.loads(result)["tags"] == ["a", "b", "c"]

    def test_keeps_list_tags(self, db_session):
        result = search.get_full_metadata(json.dumps({"tags": ["x", "y"]}), db_session)
        assert json.loads(result)["tags"] == ["x", "y"]

    def test_filters_tagged_users_to_existing(
        self,
        create_user,
        db_session,
    ):
        create_user(username="real_user")
        payload = json.dumps({"tagged_users": ["real_user", "ghost_user"]})
        result = search.get_full_metadata(payload, db_session)
        assert json.loads(result)["tagged_users"] == ["real_user"]
