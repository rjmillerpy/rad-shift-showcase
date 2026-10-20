"""Segment parsing and rule-based fallback narrative generation."""

import json

from app.chronicle.constants import (
    FALLBACK_CLOSING,
    FALLBACK_INTROS,
    FALLBACK_OPENING,
    FALLBACK_TRANSITIONS,
    MISSING_INDEX_FILLERS,
)
from app.posts.schema import PostResponse

EM_DASH = "—"


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    return text.split("\n", 1)[-1].rsplit("```", 1)[0]


def _load_json_array(text: str) -> list | None:
    """Parse `text` as a JSON array. Falls back to substring between [ ... ]."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, list) else None


def _clean_narrative(text: str) -> str:
    """Replace forbidden em-dashes with commas so the story reads uniformly."""
    return text.replace(f" {EM_DASH} ", ", ").replace(EM_DASH, ", ")


def _consume_segment(seg: dict, post_count: int, seen: set[int]) -> dict | None:
    kind = seg.get("type")
    if kind == "narrative" and "text" in seg:
        return {"type": "narrative", "text": _clean_narrative(str(seg["text"]))}
    if kind in ("post", "media") and "index" in seg:
        try:
            idx = int(seg["index"])
        except (TypeError, ValueError):
            return None
        if 0 <= idx < post_count and idx not in seen:
            seen.add(idx)
            return {"type": kind, "index": idx}
    return None


def _append_missing_indices(
    valid: list[dict],
    seen: set[int],
    post_count: int,
) -> None:
    """Ensure every post index appears, appending fillers for any that were omitted."""
    missing = [i for i in range(post_count) if i not in seen]
    for slot, idx in enumerate(missing):
        filler = MISSING_INDEX_FILLERS[slot % len(MISSING_INDEX_FILLERS)]
        valid.append({"type": "narrative", "text": filler})
        valid.append({"type": "post", "index": idx})


def parse_chronicle_segments(raw: str, post_count: int) -> list[dict] | None:
    """Parse LLM output into validated segments. Returns None on total failure."""
    parsed = _load_json_array(_strip_code_fence(raw.strip()))
    if parsed is None:
        return None

    seen: set[int] = set()
    valid: list[dict] = []
    for seg in parsed:
        if not isinstance(seg, dict):
            continue
        consumed = _consume_segment(seg, post_count, seen)
        if consumed is not None:
            valid.append(consumed)

    _append_missing_indices(valid, seen, post_count)
    return valid or None


def build_fallback_segments(posts: list[PostResponse]) -> list[dict]:
    """Rule-based narrative used when the LLM is unavailable or invalid."""
    segments: list[dict] = [{"type": "narrative", "text": FALLBACK_OPENING}]
    for i, post in enumerate(posts):
        has_media = bool(post.image_url or post.video_url or post.audio_url)
        intro = FALLBACK_INTROS[i % len(FALLBACK_INTROS)].format(u=post.username)
        segments.append({"type": "narrative", "text": intro})
        segments.append({"type": "media" if has_media else "post", "index": i})
        if i < len(posts) - 1:
            segments.append(
                {
                    "type": "narrative",
                    "text": FALLBACK_TRANSITIONS[i % len(FALLBACK_TRANSITIONS)],
                }
            )
    segments.append({"type": "narrative", "text": FALLBACK_CLOSING})
    return segments
