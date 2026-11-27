"""First-party, cookieless product analytics (app/web_analytics/).

No cookies, no stored IP addresses, no user ids: a visitor is a hash of
(that day's random salt, IP, user agent), and the salt is deleted after two
days, so a visitor can't be followed from one day to the next and nobody,
including us, can recover who they were. The same approach as Plausible's,
which is why no consent banner is needed.
"""

import re
from enum import StrEnum

# Sent by the frontend's API client: which feed mode the reader is in.
FEED_MODE_HEADER = "x-feed-mode"

# The feed modes (frontend src/app/<mode>/), plus "post" for a single post's page.
FEED_MODES = frozenset(
    {
        "lame",
        "bubbles",
        "chronicle",
        "agora",
        "mosaic",
        "ledger",
        "amble",
        "post",
        "profile",
        "search",
        "trends",
    }
)


class EventType(StrEnum):
    PAGE_VIEW = "page_view"
    ENGAGEMENT = "engagement"


class ContentSource(StrEnum):
    """Where a post came from (Phase 3 measures engagement per source)."""

    USER = "user"  # written by a person
    SCRAPED = "scraped"  # a generator source (post_metadata["source"])


# Path segments after these are ids or names: "/post/123" is stored as
# "/post/:id" and "/profile/alice" as "/profile/:name", so the table holds
# which kinds of page are read, never who looked at whom.
ID_SEGMENTS = {"post": ":id", "profile": ":name", "blog": ":slug", "widgets": ":id"}
MAX_PATH_LENGTH = 200
MAX_EVENTS_PER_BATCH = 25
MAX_BODY_BYTES = 16 * 1024

VISITOR_HASH_LENGTH = 16
SALT_BYTES = 32
# Salts older than this are deleted: yesterday's is kept so a visit that
# crosses midnight still counts once per day.
SALT_KEEP_DAYS = 2
EVENT_RETENTION_DAYS = 90
DAY_SECONDS = 86_400

# Crawlers, uptime checks and scripts are not readers.
BOT_USER_AGENT = re.compile(
    r"bot|crawl|spider|slurp|preview|monitor|uptime|headless|python|curl|wget|httpx|go-http",
    re.IGNORECASE,
)
