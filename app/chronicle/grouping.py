"""Theme-based greedy reordering so related posts sit next to each other."""

from app.chronicle.constants import (
    MIN_WORD_LEN_FOR_MATCH,
    SAME_AUTHOR_WEIGHT,
    TAG_OVERLAP_WEIGHT,
    WORD_OVERLAP_CAP,
    WORD_OVERLAP_WEIGHT,
)
from app.posts.schema import PostResponse


def _tags(post: PostResponse) -> set[str]:
    md = post.post_metadata or {}
    raw = md.get("tags", [])
    if isinstance(raw, str):
        raw = [t.strip() for t in raw.split(",") if t.strip()]
    if not raw:
        return set()
    return {t.lower() for t in raw if isinstance(t, str) and t}


def _content_words(post: PostResponse) -> set[str]:
    return {w.lower() for w in post.text.split() if len(w) > MIN_WORD_LEN_FOR_MATCH}


def _features(posts: list[PostResponse]) -> list[tuple[set[str], set[str]]]:
    """Pre-compute (tags, words) per post so similarity scoring is not O(N²) in
    tokenisation cost as well as pair count."""
    return [(_tags(p), _content_words(p)) for p in posts]


def _similarity(
    a_username: str,
    a_features: tuple[set[str], set[str]],
    b_username: str,
    b_features: tuple[set[str], set[str]],
) -> float:
    score = 0.0
    if a_username == b_username:
        score += SAME_AUTHOR_WEIGHT
    a_tags, a_words = a_features
    b_tags, b_words = b_features
    score += len(a_tags & b_tags) * TAG_OVERLAP_WEIGHT
    score += min(len(a_words & b_words) * WORD_OVERLAP_WEIGHT, WORD_OVERLAP_CAP)
    return score


def group_posts_by_theme(posts: list[PostResponse]) -> list[PostResponse]:
    """Greedy reorder: after the seed, each next post is the most-similar
    remaining one to the last placed post."""
    if len(posts) <= 2:
        return list(posts)

    features = _features(posts)
    ordered_idx = [0]
    remaining = list(range(1, len(posts)))
    while remaining:
        last_idx = ordered_idx[-1]
        best = max(
            remaining,
            key=lambda j: _similarity(
                posts[last_idx].username,
                features[last_idx],
                posts[j].username,
                features[j],
            ),
        )
        ordered_idx.append(best)
        remaining.remove(best)
    return [posts[i] for i in ordered_idx]
