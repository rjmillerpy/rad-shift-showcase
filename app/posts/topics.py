"""A post's topics: its tags and #hashtags, lowercased, for tailoring feeds.

Written once, when the post is made (posts are never edited), to the
post_topics table that app/posts/tailoring.py reads. Scraped posts get the
topics configured on their source as tags (app/generators/post_metadata.py).
"""

import json
import re
import typing
from typing import Any

from sqlalchemy.orm import Session

from .models import MAX_TOPIC_LENGTH, PostModel, PostTopic

MAX_TOPICS_PER_POST = 20
# "#rust" but not "&#39;" (an HTML entity) or "a#b" (inside a word or URL).
_HASHTAG = re.compile(rf"(?<![\w&#])#(\w{{1,{MAX_TOPIC_LENGTH}}})")


def metadata_tags(raw_meta: str | dict | None) -> list[str]:
    """A post's metadata tags: a list, or the composer's "a|b" string."""
    if not raw_meta:
        return []
    try:
        meta: Any = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except (json.JSONDecodeError, TypeError):
        return []
    tags = meta.get("tags") if isinstance(meta, dict) else None
    if isinstance(tags, str):
        tags = tags.split("|")
    if not isinstance(tags, list):
        return []
    return [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()]


def normalize_topic(raw: str) -> str | None:
    topic = raw.strip().lstrip("#").strip().lower()
    return topic[:MAX_TOPIC_LENGTH] or None


def topics_of(text: str | None, raw_meta: str | dict | None) -> list[str]:
    """Tags first, then hashtags in order, without repeats; at most MAX_TOPICS_PER_POST."""
    candidates = metadata_tags(raw_meta) + _HASHTAG.findall(text or "")
    topics: dict[str, None] = {}
    for raw in candidates:
        topic = normalize_topic(raw)
        if topic:
            topics.setdefault(topic, None)
    return list(topics)[:MAX_TOPICS_PER_POST]


def save_topics(post: PostModel, db: Session) -> None:
    """Add the post's topic rows (the post must have an id). Not committed here."""
    # PostModel uses untyped Column attributes; on an instance they are values.
    post_id = typing.cast(int, post.id)
    text = typing.cast(str | None, post.text)
    for topic in topics_of(text, typing.cast(str | dict | None, post.post_metadata)):
        db.add(PostTopic(post_id=post_id, topic=topic))
