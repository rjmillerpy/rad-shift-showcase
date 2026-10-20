"""Direct service-level unit tests for app/blog/service.py.

Content helpers live in test_content.py, view tracking in test_tracking.py,
and API-level coverage in test_views.py.
"""

import time

import pytest
from fastapi import HTTPException

from app.blog import service
from app.blog.constants import LIST_PREVIEW_LEN, MAX_SEO_TITLE_LEN, AdPlacement
from app.blog.schema import BlogCreateRequest, BlogUpdateRequest


def _create_body(**overrides) -> BlogCreateRequest:
    base = {"title": "Hello World", "content_html": "<p>Body</p>"}
    base.update(overrides)
    return BlogCreateRequest(**base)


class TestCreateBlogPost:
    def test_persists_row(self, db_session, create_user):
        user = create_user(username="creator")
        post = service.create_blog_post(user, _create_body(), db_session)
        assert post.id is not None
        assert post.user_id == user.id
        assert post.slug == "hello-world"

    def test_defaults_to_draft(self, db_session, create_user):
        user = create_user(username="drafter")
        post = service.create_blog_post(user, _create_body(is_draft=True), db_session)
        assert post.is_draft is True
        assert post.is_published is False
        assert post.published_at is None

    def test_published_when_is_draft_false(self, db_session, create_user):
        user = create_user(username="publisher")
        post = service.create_blog_post(user, _create_body(is_draft=False), db_session)
        assert post.is_draft is False
        assert post.is_published is True
        assert post.published_at is not None

    def test_slug_deduplication(self, db_session, create_user):
        user = create_user(username="dupauthor")
        p1 = service.create_blog_post(user, _create_body(title="Same"), db_session)
        p2 = service.create_blog_post(user, _create_body(title="Same"), db_session)
        p3 = service.create_blog_post(user, _create_body(title="Same"), db_session)
        assert p1.slug == "same"
        assert p2.slug == "same-2"
        assert p3.slug == "same-3"

    def test_ad_placement_forced_to_none_when_not_monetized(self, db_session, create_user):
        user = create_user(username="ads_off")
        post = service.create_blog_post(
            user,
            _create_body(monetized=False, ad_placement=AdPlacement.STANDARD),
            db_session,
        )
        assert post.ad_placement == AdPlacement.NONE.value

    def test_ad_placement_stored_when_monetized(self, db_session, create_user):
        user = create_user(username="ads_on")
        post = service.create_blog_post(
            user,
            _create_body(monetized=True, ad_placement=AdPlacement.MINIMAL),
            db_session,
        )
        assert post.ad_placement == AdPlacement.MINIMAL.value

    def test_auto_seo_title_from_title(self, db_session, create_user):
        user = create_user(username="seo_auto")
        post = service.create_blog_post(user, _create_body(title="My Long Title"), db_session)
        assert post.seo_title == "My Long Title"[:MAX_SEO_TITLE_LEN]
        assert post.og_title == "My Long Title"[:MAX_SEO_TITLE_LEN]


class TestBlogHtmlSanitized:
    DIRTY = '<p>ok</p><script>alert(1)</script><img src="x" onerror="alert(1)">'

    def test_create_sanitizes(self, db_session, create_user):
        user = create_user(username="xss_create")
        post = service.create_blog_post(user, _create_body(content_html=self.DIRTY), db_session)
        assert "<script" not in post.content_html
        assert "onerror" not in post.content_html
        assert "<p>ok</p>" in post.content_html

    def test_update_sanitizes(self, db_session, create_user):
        user = create_user(username="xss_update")
        post = service.create_blog_post(user, _create_body(), db_session)
        updated = service.update_blog_post(
            post,
            BlogUpdateRequest(content_html=self.DIRTY),
            db_session,
        )
        assert "<script" not in updated.content_html
        assert "onerror" not in updated.content_html


class TestUpdateBlogPost:
    def _seed(self, db_session, create_user, **overrides):
        user = create_user(username=overrides.pop("username", f"u{int(time.time() * 1_000_000)}"))
        post = service.create_blog_post(user, _create_body(**overrides), db_session)
        return user, post

    def test_partial_title_update(self, db_session, create_user):
        _, post = self._seed(db_session, create_user, username="edit1")
        updated = service.update_blog_post(post, BlogUpdateRequest(title="New Title"), db_session)
        assert updated.title == "New Title"

    def test_content_update_regenerates_derived_fields(self, db_session, create_user):
        _, post = self._seed(db_session, create_user, username="edit2")
        old_reading = post.reading_time_minutes
        long_html = "<p>" + " ".join(["word"] * 800) + "</p>"
        updated = service.update_blog_post(
            post, BlogUpdateRequest(content_html=long_html), db_session
        )
        assert updated.reading_time_minutes > old_reading
        assert "word" in updated.content_text

    def test_monetized_off_forces_ad_placement_none(self, db_session, create_user):
        _, post = self._seed(
            db_session,
            create_user,
            username="edit3",
            monetized=True,
            ad_placement=AdPlacement.STANDARD,
        )
        updated = service.update_blog_post(post, BlogUpdateRequest(monetized=False), db_session)
        assert updated.ad_placement == AdPlacement.NONE.value

    def test_stamps_updated_at(self, db_session, create_user):
        _, post = self._seed(db_session, create_user, username="edit4")
        original_updated_at = post.updated_at
        updated = service.update_blog_post(post, BlogUpdateRequest(title="X"), db_session)
        assert updated.updated_at != original_updated_at


class TestPublishBlogPost:
    def test_flips_flags_and_stamps(self, db_session, create_user):
        user = create_user(username="pub1")
        post = service.create_blog_post(user, _create_body(is_draft=True), db_session)
        published = service.publish_blog_post(post, db_session)
        assert published.is_published is True
        assert published.is_draft is False
        assert published.published_at is not None


class TestVisibility:
    def test_get_visible_blog_by_slug_returns_published(self, db_session, create_user):
        user = create_user(username="vis1")
        post = service.create_blog_post(user, _create_body(is_draft=False), db_session)
        assert service.get_visible_blog_by_slug(post.slug, db_session).id == post.id

    def test_get_visible_blog_by_slug_returns_draft(self, db_session, create_user):
        user = create_user(username="vis2")
        post = service.create_blog_post(user, _create_body(is_draft=True), db_session)
        assert service.get_visible_blog_by_slug(post.slug, db_session).id == post.id

    def test_get_visible_blog_missing_slug_404(self, db_session):
        with pytest.raises(HTTPException) as exc:
            service.get_visible_blog_by_slug("does-not-exist", db_session)
        assert exc.value.status_code == 404

    def test_get_visible_blog_rejected_when_hidden(self, db_session, create_user):
        """Blog neither draft nor published — treated as absent."""
        user = create_user(username="vis3")
        post = service.create_blog_post(user, _create_body(is_draft=True), db_session)
        post.is_draft = False
        post.is_published = False
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            service.get_visible_blog_by_slug(post.slug, db_session)
        assert exc.value.status_code == 404


class TestListBlogPosts:
    def test_pagination(self, db_session, create_user):
        user = create_user(username="lister")
        for i in range(4):
            service.create_blog_post(user, _create_body(title=f"P{i}", is_draft=False), db_session)
        posts, has_more = service.list_blog_posts(db_session, offset=0, limit=2)
        assert len(posts) == 2
        assert has_more is True

    def test_user_filter(self, db_session, create_user):
        a = create_user(username="lister_a")
        b = create_user(username="lister_b")
        service.create_blog_post(a, _create_body(title="A", is_draft=False), db_session)
        service.create_blog_post(b, _create_body(title="B", is_draft=False), db_session)
        posts, _ = service.list_blog_posts(db_session, user_id=a.id)
        assert [p.user_id for p in posts] == [a.id]

    def test_published_only_default(self, db_session, create_user):
        user = create_user(username="lister_pub")
        service.create_blog_post(user, _create_body(title="Live", is_draft=False), db_session)
        service.create_blog_post(user, _create_body(title="Draft", is_draft=True), db_session)
        posts, _ = service.list_blog_posts(db_session, user_id=user.id)
        titles = {p.title for p in posts}
        assert titles == {"Live"}

    def test_published_only_false_returns_all(self, db_session, create_user):
        user = create_user(username="lister_all")
        service.create_blog_post(user, _create_body(title="Live", is_draft=False), db_session)
        service.create_blog_post(user, _create_body(title="Draft", is_draft=True), db_session)
        posts, _ = service.list_blog_posts(db_session, user_id=user.id, published_only=False)
        assert len(posts) == 2


class TestBlogPostToDict:
    def test_full_content_by_default(self, db_session, create_user):
        user = create_user(username="ser1")
        post = service.create_blog_post(user, _create_body(), db_session)
        data = service.blog_post_to_dict(post)
        assert "content_html" in data
        assert "content_text" in data
        assert "preview" not in data
        assert data["username"] == user.username

    def test_preview_when_content_excluded(self, db_session, create_user):
        user = create_user(username="ser2")
        long_html = "<p>" + ("x" * (LIST_PREVIEW_LEN * 2)) + "</p>"
        post = service.create_blog_post(user, _create_body(content_html=long_html), db_session)
        data = service.blog_post_to_dict(post, include_content=False)
        assert "content_html" not in data
        assert len(data["preview"]) == LIST_PREVIEW_LEN
