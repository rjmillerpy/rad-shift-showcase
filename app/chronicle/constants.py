"""Constants for the chronicle domain.

One source of truth for LLM model config, cache TTL, similarity weights,
and the filler/intro/transition text pools used by the rule-based fallback.
"""

CHRONICLE_MODEL = "claude-haiku-4-5-20251001"
CHRONICLE_MAX_TOKENS = 2048
CHRONICLE_CACHE_SECONDS = 3600
CHRONICLE_CONTEXT_CHARS = 120
CHRONICLE_BATCH_SIZE = 4

# Upper bound on posts per chronicle page. Each CHRONICLE_BATCH_SIZE posts cost
# one LLM call, and the endpoints are public, so this caps per-request spend
# (20 posts = 5 calls). The frontend requests 8 (12 on the fallback path).
CHRONICLE_MAX_POSTS_PER_PAGE = 20
CHRONICLE_DEFAULT_POSTS_PER_PAGE = 8

# Anthropic client timeout for both non-streaming and streaming calls.
ANTHROPIC_TIMEOUT_SECONDS = 30

# Post similarity scoring weights (used by grouping.py). Larger = stronger pull
# to place two posts adjacent in the chronicle.
SAME_AUTHOR_WEIGHT = 2.0
TAG_OVERLAP_WEIGHT = 1.5
WORD_OVERLAP_WEIGHT = 0.3
WORD_OVERLAP_CAP = 2.0

# Only words strictly longer than this are considered for overlap scoring; short
# tokens (the, and, on) contribute noise.
MIN_WORD_LEN_FOR_MATCH = 3

# Fallback narrative fillers used when the LLM omits indices or is unavailable.
MISSING_INDEX_FILLERS: tuple[str, ...] = (
    "There was more to read. ",
    "The topic shifted. ",
    "Something else followed. ",
    "A different take came next. ",
)

FALLBACK_INTROS: tuple[str, ...] = (
    "As @{u} reflected on the matter, ",
    "It was @{u} who offered a thought worth considering: ",
    "@{u} observed something that caught the attention of many: ",
    "Few could have said it better than @{u}, who wrote ",
    "Adding to the conversation, @{u} remarked ",
    "@{u} mused on the subject with characteristic clarity: ",
    "In a quieter corner, @{u} shared ",
    "@{u} continued with a thought of their own: ",
)

FALLBACK_TRANSITIONS: tuple[str, ...] = (
    "The sentiment lingered. ",
    "A moment passed before the next voice arrived. ",
    "The conversation shifted, finding new ground. ",
    "There was more to be said on the matter. ",
    "The chronicle pressed on. ",
    "Another perspective emerged. ",
)

FALLBACK_OPENING = "The day brought with it a chorus of voices, each adding something new. "
FALLBACK_CLOSING = "That was enough for one sitting. The rest could wait."
