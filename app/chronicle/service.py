"""Chronicle orchestration — fetch posts, batch through Haiku, cache, emit."""

import json
import logging
from collections.abc import Iterator
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.auth.models import User
from app.chronicle import cache
from app.chronicle.client import call_haiku, stream_haiku
from app.chronicle.constants import (
    CHRONICLE_BATCH_SIZE,
    CHRONICLE_CONTEXT_CHARS,
)
from app.chronicle.grouping import group_posts_by_theme
from app.chronicle.parsing import build_fallback_segments, parse_chronicle_segments
from app.flags.constants import Flag
from app.flags.service import is_enabled
from app.plugins import edition
from app.posts.feeds import get_algo_posts_formatted
from app.posts.schema import PostResponse

logger = logging.getLogger(__name__)


def _prepare(
    db: Session,
    current_user: User | None,
    page: int,
    posts_per_page: int,
    narrated: bool,
) -> tuple[list[PostResponse], bool, str]:
    """Fetch algo posts for the page, reorder by theme, compute cache key."""
    offset = page * posts_per_page
    posts, has_more = get_algo_posts_formatted(
        db=db,
        current_user=current_user,
        offset=offset,
        limit=posts_per_page,
    )
    if not posts:
        return [], has_more, ""
    ordered = group_posts_by_theme(posts)
    return ordered, has_more, cache.cache_key_for(ordered, narrated=narrated)


def _reindex_batch(batch_segments: list[dict], batch_start: int) -> None:
    """Convert local indices returned by the parser into global chronicle indices."""
    for seg in batch_segments:
        if seg.get("type") in ("post", "media") and "index" in seg:
            seg["index"] = seg["index"] + batch_start


def _tail_context(batch_segments: list[dict]) -> str:
    """Return the trailing narrative text (capped) so the next batch can continue."""
    narratives = [s for s in batch_segments if s.get("type") == "narrative"]
    if not narratives:
        return ""
    return narratives[-1]["text"][-CHRONICLE_CONTEXT_CHARS:]


def _batches(posts: list[PostResponse]) -> Iterator[tuple[int, list[PostResponse]]]:
    for batch_start in range(0, len(posts), CHRONICLE_BATCH_SIZE):
        yield batch_start, posts[batch_start : batch_start + CHRONICLE_BATCH_SIZE]


def _parse_or_fallback(raw: str, batch: list[PostResponse]) -> list[dict]:
    if raw:
        parsed = parse_chronicle_segments(raw, len(batch))
        if parsed:
            return parsed
    return build_fallback_segments(batch)


def generate_chronicle(
    db: Session,
    current_user: User | None = None,
    page: int = 0,
    posts_per_page: int = 8,
) -> dict:
    """Generate a chronicle chapter using Anthropic Haiku, cached per post set.

    Without the chronicle-llm-narration flag, every batch gets the rule-based
    narration and no LLM call is made.
    """
    narrated = is_enabled(Flag.CHRONICLE_LLM_NARRATION, current_user)
    posts, has_more, cache_key = _prepare(db, current_user, page, posts_per_page, narrated)
    if not posts:
        return {"segments": [], "posts": [], "page": page, "has_more": False, "cached": False}

    cached_segments = cache.get(cache_key)
    if cached_segments is not None:
        return {
            "segments": cached_segments,
            "posts": [asdict(p) for p in posts],
            "page": page,
            "has_more": has_more,
            "cached": True,
        }

    all_segments: list[dict] = []
    prev_context = ""
    prompts = edition().chronicle_prompt
    for batch_start, batch in _batches(posts):
        prompt = prompts.build_batch_prompt(batch, batch_start, len(posts), prev_context)
        raw = call_haiku(prompt, prompts.system) if narrated else None
        batch_segments = _parse_or_fallback(raw or "", batch)
        _reindex_batch(batch_segments, batch_start)
        prev_context = _tail_context(batch_segments) or prev_context
        all_segments.extend(batch_segments)

    cache.store(cache_key, all_segments)
    return {
        "segments": all_segments,
        "posts": [asdict(p) for p in posts],
        "page": page,
        "has_more": has_more,
        "cached": False,
    }


def _sse_line(payload: dict) -> str:
    return json.dumps(payload) + "\n"


def stream_chronicle(
    db: Session,
    current_user: User | None = None,
    page: int = 0,
    posts_per_page: int = 8,
) -> Iterator[str]:
    """Stream a chronicle chapter using Haiku, emitting NDJSON events.

    Without the chronicle-llm-narration flag no tokens are streamed: each
    batch's rule-based segments arrive directly.
    """
    narrated = is_enabled(Flag.CHRONICLE_LLM_NARRATION, current_user)
    posts, has_more, cache_key = _prepare(db, current_user, page, posts_per_page, narrated)
    if not posts:
        yield _sse_line({"type": "init", "posts": [], "page": page, "has_more": False})
        yield _sse_line({"type": "done", "segments": []})
        return

    yield _sse_line(
        {
            "type": "init",
            "posts": [asdict(p) for p in posts],
            "page": page,
            "has_more": has_more,
        }
    )

    cached_segments = cache.get(cache_key)
    if cached_segments is not None:
        yield _sse_line({"type": "done", "segments": cached_segments, "cached": True})
        return

    all_segments: list[dict] = []
    prev_context = ""
    prompts = edition().chronicle_prompt
    for batch_start, batch in _batches(posts):
        prompt = prompts.build_batch_prompt(batch, batch_start, len(posts), prev_context)

        accumulated = ""
        for token in stream_haiku(prompt, prompts.system) if narrated else ():
            accumulated += token
            yield _sse_line({"type": "token", "token": token})

        batch_segments = _parse_or_fallback(accumulated, batch)
        _reindex_batch(batch_segments, batch_start)
        prev_context = _tail_context(batch_segments) or prev_context

        for seg in batch_segments:
            yield _sse_line({"type": "segment", "segment": seg})
        all_segments.extend(batch_segments)

    cache.store(cache_key, all_segments)
    yield _sse_line({"type": "done", "segments": all_segments})
