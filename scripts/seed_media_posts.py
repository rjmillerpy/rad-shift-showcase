"""Seed the database with test posts containing audio and video URLs.

Usage:
    .venv/bin/python scripts/seed_media_posts.py

Requires the backend to be able to connect to the database.
Uses publicly available sample media from Mozilla and W3Schools.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth.models import User
from app.common.db import SessionLocal
from app.posts.models import PostModel

SAMPLE_AUDIO = [
    {
        "text": "Check out this ambient track I found — great for coding sessions",
        "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "media_metadata": {
            "duration_seconds": 375.0,
            "bitrate": 128000,
            "sample_rate": 44100,
            "format": "mp3",
            "type": "audio",
        },
    },
    {
        "text": "Short drum loop — free to use in your projects",
        "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "media_metadata": {
            "duration_seconds": 342.0,
            "bitrate": 128000,
            "sample_rate": 44100,
            "format": "mp3",
            "type": "audio",
        },
    },
    {
        "text": "Here's a mellow piano piece I've been listening to on repeat",
        "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3",
        "media_metadata": {
            "duration_seconds": 295.0,
            "bitrate": 128000,
            "sample_rate": 44100,
            "format": "mp3",
            "type": "audio",
        },
    },
]

SAMPLE_VIDEO = [
    {
        "text": "Big Buck Bunny — open source animated short. The classic!",
        "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
        "media_metadata": {
            "duration_seconds": 596.0,
            "bitrate": 2100000,
            "dimensions": {"width": 1280, "height": 720},
            "format": "mp4",
            "type": "video",
        },
    },
    {
        "text": "Elephant's Dream — first Blender open movie",
        "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
        "media_metadata": {
            "duration_seconds": 653.0,
            "bitrate": 2400000,
            "dimensions": {"width": 1280, "height": 720},
            "format": "mp4",
            "type": "video",
        },
    },
    {
        "text": "Quick nature clip to brighten your feed",
        "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
        "media_metadata": {
            "duration_seconds": 15.0,
            "bitrate": 800000,
            "dimensions": {"width": 1280, "height": 720},
            "format": "mp4",
            "type": "video",
        },
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        # Find the first user to attach posts to
        user = db.query(User).first()
        if not user:
            print("ERROR: No users in database. Sign up first, then re-run this script.")
            return

        print(f"Using user: @{user.username} (id={user.id})")

        now = int(time.time())
        created = 0

        for i, item in enumerate(SAMPLE_AUDIO):
            post = PostModel(
                text=item["text"],
                post_metadata="{}",
                unix_timestamp=now - (i * 120),
                user_id=user.id,
                audio_url=item["audio_url"],
                media_metadata=item["media_metadata"],
            )
            db.add(post)
            created += 1

        for i, item in enumerate(SAMPLE_VIDEO):
            post = PostModel(
                text=item["text"],
                post_metadata="{}",
                unix_timestamp=now - ((i + len(SAMPLE_AUDIO)) * 120),
                user_id=user.id,
                video_url=item["video_url"],
                media_metadata=item["media_metadata"],
            )
            db.add(post)
            created += 1

        db.commit()
        print(
            f"Created {created} media posts ({len(SAMPLE_AUDIO)} audio + {len(SAMPLE_VIDEO)} video)"
        )

    finally:
        db.close()


if __name__ == "__main__":
    seed()
