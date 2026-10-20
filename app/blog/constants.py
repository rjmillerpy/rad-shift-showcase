"""Shared constants for the blog domain."""

from enum import Enum

MAX_TITLE_LEN = 500
MAX_SLUG_LEN = 200
MAX_SEO_TITLE_LEN = 255
MAX_SEO_DESCRIPTION_LEN = 500
MAX_CATEGORY_LEN = 100

WORDS_PER_MINUTE = 200

SEO_DESC_MAX_LEN = 160
SEO_DESC_ELLIPSIS = "..."
SEO_DESC_TRUNCATE_AT = SEO_DESC_MAX_LEN - len(SEO_DESC_ELLIPSIS)

LIST_PREVIEW_LEN = 200
IP_HASH_LEN = 16

MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 20
MAX_USERNAME_FILTER_LEN = 80

# Cap read-time reports to a plausible upper bound so a malicious client can't
# skew analytics with billion-second values.
MAX_READ_TIME_SECONDS = 24 * 60 * 60  # one day


class AdPlacement(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    STANDARD = "standard"
