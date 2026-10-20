"""Shared builders for the chronicle tests."""

from app.posts.schema import PostResponse


def make_post(
    id: int = 1,
    username: str = "alice",
    text: str = "hello",
    tags: list[str] | str | None = None,
    image_url: str | None = None,
    video_url: str | None = None,
    audio_url: str | None = None,
) -> PostResponse:
    metadata: dict = {}
    if tags is not None:
        metadata["tags"] = tags
    return PostResponse(
        id=id,
        text=text,
        likes=0,
        shares=0,
        reposts=0,
        saves=0,
        laughs=0,
        liked_by_me=False,
        unix_timestamp=1_700_000_000,
        post_metadata=metadata,
        username=username,
        profile_picture_url=None,
        image_url=image_url,
        video_url=video_url,
        audio_url=audio_url,
    )
