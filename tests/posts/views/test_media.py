"""Tests for app/posts — GET /posts/media endpoint (media-filtered feed)."""

import pytest


class TestMediaEndpoint:
    """Tests for GET /posts/media — media-filtered feed."""

    def _create_media_posts(self, create_user, create_post, db_session):
        """Helper: create posts with audio_url, video_url, both, and neither."""
        user = create_user(username="mediaposter")
        audio_post = create_post(user=user, text="audio post")
        audio_post.audio_url = "https://example.com/song.mp3"
        video_post = create_post(user=user, text="video post")
        video_post.video_url = "https://example.com/clip.mp4"
        both_post = create_post(user=user, text="both media")
        both_post.audio_url = "https://example.com/track.ogg"
        both_post.video_url = "https://example.com/vid.webm"
        text_post = create_post(user=user, text="text only")
        db_session.commit()
        return user, audio_post, video_post, both_post, text_post

    def test_media_returns_only_media_posts(self, client, create_user, create_post, db_session):
        """GET /posts/media returns posts with audio or video, excludes text-only."""
        _, audio_post, video_post, both_post, text_post = self._create_media_posts(
            create_user,
            create_post,
            db_session,
        )
        resp = client.get("/posts/media")
        assert resp.status_code == 200
        posts = resp.json()["posts"]
        post_ids = {p["id"] for p in posts}
        assert audio_post.id in post_ids
        assert video_post.id in post_ids
        assert both_post.id in post_ids
        assert text_post.id not in post_ids

    @pytest.mark.parametrize(
        "media_type,expected_text,excluded_text",
        [
            ("audio", {"audio post", "both media"}, {"video post", "text only"}),
            ("video", {"video post", "both media"}, {"audio post", "text only"}),
        ],
        ids=["filter-audio-only", "filter-video-only"],
    )
    def test_media_filter_by_type(
        self,
        client,
        create_user,
        create_post,
        db_session,
        media_type,
        expected_text,
        excluded_text,
    ):
        """GET /posts/media?media_type=audio|video filters correctly."""
        self._create_media_posts(create_user, create_post, db_session)
        resp = client.get(f"/posts/media?media_type={media_type}")
        assert resp.status_code == 200
        texts = {p["text"] for p in resp.json()["posts"]}
        for expected in expected_text:
            assert expected in texts
        for excluded in excluded_text:
            assert excluded not in texts

    def test_media_pagination(self, client, create_user, create_post, db_session):
        """Pagination with offset and limit returns correct slices."""
        user = create_user(username="paginator")
        for i in range(5):
            p = create_post(user=user, text=f"audio {i}")
            p.audio_url = f"https://example.com/a{i}.mp3"
        db_session.commit()

        resp_page1 = client.get("/posts/media?offset=0&limit=2")
        assert resp_page1.status_code == 200
        data1 = resp_page1.json()
        assert len(data1["posts"]) == 2
        assert data1["has_more"] is True

        resp_page2 = client.get("/posts/media?offset=2&limit=2")
        data2 = resp_page2.json()
        assert len(data2["posts"]) == 2
        assert data2["has_more"] is True

        resp_page3 = client.get("/posts/media?offset=4&limit=2")
        data3 = resp_page3.json()
        assert len(data3["posts"]) == 1
        assert data3["has_more"] is False

    def test_media_excludes_drafts(self, client, create_user, create_post, db_session):
        """Draft posts with media are excluded from the media feed."""
        user = create_user(username="drafter")
        draft = create_post(user=user, text="draft audio", is_draft=True)
        draft.audio_url = "https://example.com/draft.mp3"
        db_session.commit()
        resp = client.get("/posts/media")
        assert resp.status_code == 200
        assert len(resp.json()["posts"]) == 0
