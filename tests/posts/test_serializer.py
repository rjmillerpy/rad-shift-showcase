"""Tests for app/posts/serializer.py — batch PostResponse construction."""

from app.posts import serializer
from app.posts.models import PostModel


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

    def test_image_variants_are_passed_through(self, create_user, create_post, db_session):
        """Recorded by the media pipeline (app/media/); absent until then."""
        post = create_post(user=create_user(username="ser_variants"))
        (before,) = serializer.build_post_responses([post], None, db_session)
        variants = {"https://b.s3.amazonaws.com/posts/a.jpg": {"480": "https://b/v-480.webp"}}
        post.image_variants = variants
        db_session.commit()
        (after,) = serializer.build_post_responses([post], None, db_session)
        assert (before.image_variants, after.image_variants) == (None, variants)

    def test_backwards_compat_alias(self):
        assert serializer._build_post_responses is serializer.build_post_responses


class TestByActiveAuthors:
    def test_leaves_out_banned_authors_posts_only(self, db_session, create_user, create_post):
        kept = create_post(user=create_user(username="member"), text="kept")
        banned = create_user(username="banned")
        create_post(user=banned, text="hidden")
        banned.is_banned = True
        db_session.commit()

        posts = serializer.by_active_authors(db_session.query(PostModel)).all()

        assert [p.id for p in posts] == [kept.id]

    def test_unbanning_brings_them_back(self, db_session, create_user, create_post):
        author = create_user(username="author")
        post = create_post(user=author)
        author.is_banned = True
        db_session.commit()
        author.is_banned = False
        db_session.commit()

        assert serializer.by_active_authors(db_session.query(PostModel)).all() == [post]
