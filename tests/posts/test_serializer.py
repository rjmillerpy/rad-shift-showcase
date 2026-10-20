"""Tests for app/posts/serializer.py — batch PostResponse construction."""

from app.posts import serializer


class TestGetOrderedModel:
    def test_desc(self):
        # The clause's __clause_element__ carries the ordering; string form is stable.
        clause = serializer.get_ordered_model(desc=True)
        assert "DESC" in str(clause).upper()

    def test_asc(self):
        clause = serializer.get_ordered_model(desc=False)
        assert "ASC" in str(clause).upper()


class TestGetMetadata:
    def test_valid_json(self, create_user, create_post):
        user = create_user(username="ser_meta")
        post = create_post(user=user, metadata={"tags": ["a", "b"]})
        result = serializer.get_metadata(post)
        assert result == {"tags": ["a", "b"]}

    def test_empty_returns_empty_dict(self, create_user, create_post, db_session):
        user = create_user(username="ser_empty")
        post = create_post(user=user)
        post.post_metadata = None
        db_session.commit()
        assert serializer.get_metadata(post) == {}

    def test_malformed_json_returns_empty_dict(self, create_user, create_post, db_session):
        user = create_user(username="ser_bad")
        post = create_post(user=user)
        post.post_metadata = "{not json"
        db_session.commit()
        assert serializer.get_metadata(post) == {}


class TestBuildQuotedPost:
    def test_none_when_no_parent(self, create_user, create_post):
        user = create_user(username="ser_quote_none")
        post = create_post(user=user)
        assert serializer.build_quoted_post(post) is None

    def test_returns_parent_info(self, create_user, create_post, db_session):
        user = create_user(username="ser_quote_parent")
        parent = create_post(user=user, text="parent text")
        child = create_post(user=user, text="child", parent_post_id=parent.id)
        # relationship needs a refresh so `parent_post` resolves
        db_session.refresh(child)
        result = serializer.build_quoted_post(child)
        assert result == {"id": parent.id, "username": user.username, "text": "parent text"}


class TestBuildPostResponses:
    def test_empty_input(self, db_session):
        assert serializer.build_post_responses([], None, db_session) == []

    def test_returns_one_response_per_post(
        self,
        create_user,
        create_post,
        db_session,
    ):
        user = create_user(username="ser_batch")
        p1 = create_post(user=user, text="one")
        p2 = create_post(user=user, text="two")
        results = serializer.build_post_responses([p1, p2], None, db_session)
        assert [r.id for r in results] == [p1.id, p2.id]

    def test_liked_by_me_when_current_user_has_liked(
        self,
        create_user,
        create_post,
        db_session,
    ):
        from app.posts.models import PostLike

        author = create_user(username="ser_liked_author")
        reader = create_user(username="ser_liked_reader")
        post = create_post(user=author, text="liked")
        db_session.add(PostLike(user_id=reader.id, post_id=post.id))
        db_session.commit()
        results = serializer.build_post_responses([post], reader, db_session)
        assert results[0].liked_by_me is True

    def test_saved_override_forces_is_saved_by_me(
        self,
        create_user,
        create_post,
        db_session,
    ):
        author = create_user(username="ser_saved_author")
        reader = create_user(username="ser_saved_reader")
        post = create_post(user=author)
        results = serializer.build_post_responses(
            [post],
            reader,
            db_session,
            saved_override=True,
        )
        assert results[0].is_saved_by_me is True

    def test_backwards_compat_alias(self):
        assert serializer._build_post_responses is serializer.build_post_responses
